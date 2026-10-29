import copy
import hashlib
import json

import pytest

import minerva_dataset as dataset
from minerva_hybrid import _fusao_rrf
from minerva_static import snapshot_verificado


@pytest.fixture
def aprovado(tmp_path, monkeypatch):
    texto = b"Fonte institucional de teste"
    (tmp_path / "fonte.txt").write_bytes(texto)
    entrada = {
        "id": "TESTE", "url_oficial": "https://fct.ufpa.br/",
        "resposta_literal": "Resposta revisada.", "temporal": False,
        "estrategia_recuperacao": "RESPOSTA_LITERAL", "pergunta": "Pergunta?",
    }
    manifesto = {"TESTE": {
        "file": "fonte.txt", "url": entrada["url_oficial"],
        "sha256": hashlib.sha256(texto).hexdigest(),
        "answer_sha256": hashlib.sha256(b"Resposta revisada.").hexdigest(),
    }}
    (tmp_path / "static_manifest.json").write_text(json.dumps(manifesto))
    monkeypatch.setenv("MINERVA_V7_STATIC_SNAPSHOT_DIR", str(tmp_path))
    return entrada, manifesto, tmp_path


def test_rrf_duplicado_nao_ganha_pontos_e_nao_altera_entrada():
    a = {"id": 1, "titulo": "A", "trecho": "A"}
    b = {"id": 2, "titulo": "B", "trecho": "B"}
    listas = ([a, a, b], [b])
    original = copy.deepcopy(listas)
    assert _fusao_rrf(*listas)[0]["titulo"] == "B"
    assert listas == original
    assert _fusao_rrf(*listas) == _fusao_rrf(*listas)


def test_rrf_desempate_por_id_independe_da_ordem_das_listas():
    a = {"id": 9, "titulo": "A", "trecho": "A"}
    b = {"id": 2, "titulo": "B", "trecho": "B"}
    assert _fusao_rrf([a, b], [b, a]) == _fusao_rrf([b, a], [a, b])
    assert _fusao_rrf([a, b], [b, a])[0]["titulo"] == "B"


def test_snapshot_aprovado_libera_resposta_com_fonte(aprovado):
    entrada, _, _ = aprovado
    assert snapshot_verificado(entrada)
    assert dataset._resposta_literal(entrada) == (
        "Resposta revisada.\nFonte oficial: https://fct.ufpa.br/"
    )


@pytest.mark.parametrize("alteracao", [
    {"temporal": True}, {"temporal": "false"},
    {"url_oficial": "https://ufpa.br.exemplo.com/"},
    {"url_oficial": "http://fct.ufpa.br/"},
    {"resposta_literal": "Resposta alterada."}, {"id": "OUTRA"},
])
def test_snapshot_rejeita_entrada_alterada(aprovado, alteracao):
    entrada, _, _ = aprovado
    assert not snapshot_verificado({**entrada, **alteracao})


@pytest.mark.parametrize("valor", [None, [], "texto", {"TESTE": []}])
def test_manifesto_malformado_falha_fechado(aprovado, valor):
    entrada, _, root = aprovado
    (root / "static_manifest.json").write_text(json.dumps(valor))
    assert not snapshot_verificado(entrada)


def test_fonte_alterada_revoga_resposta(aprovado):
    entrada, _, root = aprovado
    (root / "fonte.txt").write_text("alterado")
    assert dataset._resposta_literal(entrada) is None


def test_sem_configuracao_nao_responde(aprovado, monkeypatch):
    entrada, _, _ = aprovado
    monkeypatch.delenv("MINERVA_V7_STATIC_SNAPSHOT_DIR")
    assert dataset._resposta_literal(entrada) is None


def test_snapshot_nao_aceita_escape_por_symlink(aprovado, tmp_path_factory):
    entrada, manifesto, root = aprovado
    fora = tmp_path_factory.mktemp("fora") / "fonte.txt"
    fora.write_bytes((root / "fonte.txt").read_bytes())
    (root / "atalho.txt").symlink_to(fora)
    manifesto["TESTE"]["file"] = "atalho.txt"
    (root / "static_manifest.json").write_text(json.dumps(manifesto))
    assert not snapshot_verificado(entrada)


def test_dataset_sem_snapshot_retorna_para_rag(aprovado, monkeypatch):
    entrada, _, _ = aprovado
    monkeypatch.delenv("MINERVA_V7_STATIC_SNAPSHOT_DIR")
    monkeypatch.setattr(dataset, "_carregar_entradas", lambda: [entrada])
    monkeypatch.setattr(dataset, "_resposta_conhecida", lambda e: pytest.fail("atalho indevido"))
    monkeypatch.setattr(dataset, "_resposta_via_fetch", lambda e: pytest.fail("fetch indevido"))
    assert dataset.resposta_dataset("Pergunta?") is None


def test_estrategia_web_nao_usa_resposta_literal(aprovado, monkeypatch):
    entrada, _, _ = aprovado
    entrada["estrategia_recuperacao"] = "RAG_WEB_CONTROLADO"
    monkeypatch.setattr(dataset, "_carregar_entradas", lambda: [entrada])
    monkeypatch.setattr(dataset, "_resposta_via_fetch", lambda e: "Consulte a fonte.")
    assert dataset.resposta_dataset("Pergunta?") == "Consulte a fonte."
