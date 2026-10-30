import copy
import hashlib
import json
from pathlib import Path

import pytest

from minerva_dataset import entrada_contextual, perguntas_relacionadas, _pergunta_bate, _norm
from minerva_qa_catalogo import validar_dataset, sincronizar_catalogo
from scripts import ingestao as ing
from .test_ingestao import Modelo


def dataset_real():
    return json.loads((Path(__file__).parents[1]/"minerva_dataset.json").read_text())


def test_contextos_variacoes_e_relacoes_do_dataset_sao_consistentes():
    entradas=validar_dataset(dataset_real())
    es={e["id"]:e for e in entradas}
    assert all(es[f"MINERVA_{i:04d}"].get("contexto_documental") for i in range(6,93))
    assert not es["MINERVA_0055"]["ativo"]
    for e in entradas:
        if e.get("contexto_documental"):
            assert e["autorizacao_literal"]=="pendente"
            assert e["contexto_documental"]["evidencias"]
            if e.get("ativo",True):
                assert len(e["variacoes"])>=2
                assert entrada_contextual(e["pergunta"])["id"]==e["id"]
                for v in e["variacoes"]:
                    assert entrada_contextual(v)["id"]==e["id"]


def test_pergunta_deitica_nao_herda_contexto_indevido():
    assert entrada_contextual("Qual é a função do item VIII?") is None
    assert entrada_contextual("O que o conselho pode decidir sobre?") is None
    e=entrada_contextual("Quem acompanha e informa a tramitação de documentos no regimento local da faculdade?")
    assert e["id"]=="MINERVA_0027" and "Secretaria Executiva" in e["resposta_literal"]
    assert not _pergunta_bate(_norm("conselho faculdade palavra aleatória"),e)


def test_ramificacao_nao_e_confundida_com_parafrase():
    es={e["id"]:e for e in dataset_real()["respostas_especificas"]}
    base=es["MINERVA_0067"]
    relacionadas=perguntas_relacionadas(base["pergunta"])
    assert {"MINERVA_0081","MINERVA_0082"} <= {r["id"] for r in relacionadas}
    assert entrada_contextual(es["MINERVA_0081"]["pergunta"])["id"]!="MINERVA_0067"


def test_condicoes_e_orgaos_corrigidos_nao_sao_generalizados():
    es={e["id"]:e for e in dataset_real()["respostas_especificas"]}
    assert "sindicância" in es["MINERVA_0051"]["resposta_literal"]
    assert "sem justificação aceita" in es["MINERVA_0056"]["resposta_literal"]
    assert "membro nato" in es["MINERVA_0056"]["resposta_literal"]
    assert "emitir parecer" in es["MINERVA_0054"]["resposta_literal"]
    assert "Secretaria Executiva" in es["MINERVA_0027"]["resposta_literal"]
    assert "Câmara de Legislação e Normas" in es["MINERVA_0041"]["resposta_literal"]
    assert "Telecomunicações" in es["MINERVA_0070"]["contexto_documental"]["escopo"]


@pytest.fixture
def catalogo(pdfs):
    texto=(pdfs/"a.pdf").read_text()
    sha=hashlib.sha256((pdfs/"a.pdf").read_bytes()).hexdigest()
    base={"id":"Q1","pergunta":"Qual é a regra do documento A?","resposta_literal":texto,
          "ativo":True,"variacoes":["Que regra consta no documento A?"],"fonte_documento":"a.pdf",
          "contexto_documental":{"documento":"a.pdf","documento_sha256":sha,"escopo":"teste",
          "dispositivo":"seção de teste","paginas_fisicas":[1],"evidencias":[{"pagina_fisica":1,"texto":texto,"texto_sha256":hashlib.sha256(texto.encode()).hexdigest()}]},
          "relacoes":[{"id":"Q2","tipo":"assunto_relacionado","motivo":"mesmo documento"}]}
    outra=copy.deepcopy(base)
    outra.update(id="Q2",pergunta="Qual documento contém a regra A?",variacoes=[],relacoes=[])
    return {"versao_dataset":"teste","respostas_especificas":[base,outra]}


def test_publicacao_qa_idempotente_e_vincula_evidencias(banco,pdfs,catalogo):
    ing.atualizar_corpus(banco,pdfs,Modelo)
    a=sincronizar_catalogo(banco,catalogo)
    b=sincronizar_catalogo(banco,catalogo)
    assert a==b
    assert a["minerva_perguntas_respostas"]==2 and a["minerva_qa_relacoes"]==1
    assert a["minerva_qa_evidencias"]==2
    with banco.cursor() as cur:
        cur.execute("SELECT count(*) FROM minerva_qa_versoes")
        assert cur.fetchone()[0]==1
        cur.execute("SELECT count(*) FROM documentos_ufpa")
        assert cur.fetchone()[0]==1 # Perguntas não viram evidências factuais.


def test_versao_divergente_reverte_publicacao_qa(banco,pdfs,catalogo):
    ing.atualizar_corpus(banco,pdfs,Modelo)
    antes=sincronizar_catalogo(banco,catalogo)
    errado=copy.deepcopy(catalogo)
    errado["respostas_especificas"][0]["resposta_literal"]="Alterada antes da falha"
    errado["respostas_especificas"][1]["contexto_documental"]["documento_sha256"]="0"*64
    with pytest.raises(ValueError,match="Versão do corpus"):
        sincronizar_catalogo(banco,errado)
    with banco.cursor() as cur:
        cur.execute("SELECT resposta FROM minerva_perguntas_respostas WHERE id='Q1'")
        assert cur.fetchone()[0]==catalogo["respostas_especificas"][0]["resposta_literal"]
        cur.execute("SELECT count(*) FROM minerva_qa_versoes")
        assert cur.fetchone()[0]==1
    assert sincronizar_catalogo(banco,catalogo)==antes


def test_alias_ambiguo_ou_relacao_orfa_sao_rejeitados(catalogo):
    errado=copy.deepcopy(catalogo)
    errado["respostas_especificas"][1]["variacoes"]=[catalogo["respostas_especificas"][0]["pergunta"]]
    with pytest.raises(ValueError,match="Variação ambígua"):
        validar_dataset(errado)
    catalogo["respostas_especificas"][0]["relacoes"][0]["id"]="INEXISTENTE"
    with pytest.raises(ValueError,match="Relação sem destino"):
        validar_dataset(catalogo)


def test_busca_contextual_nao_reutiliza_versao_antiga(banco,pdfs,catalogo,monkeypatch):
    import minerva_hybrid as rag
    ing.atualizar_corpus(banco,pdfs,Modelo)
    e=catalogo["respostas_especificas"][0]
    e["pergunta"]="Texto institucional de teste"
    monkeypatch.setattr("minerva_dataset.entrada_contextual",lambda q:e)
    monkeypatch.setattr(rag,"_get_embedding_model",lambda:None)
    fontes=rag.buscar_em_documentos_postgres(banco,"Variação da pergunta")
    assert len(fontes)==1 and fontes[0]["titulo"]=="a.pdf"
    e["contexto_documental"]["documento_sha256"]="0"*64
    assert rag.buscar_em_documentos_postgres(banco,"Variação da pergunta")==[]


def test_contexto_explicito_recupera_formulario_sem_reduzir_limiar_global(banco,pdfs,catalogo,monkeypatch):
    import minerva_hybrid as rag
    ing.atualizar_corpus(banco,pdfs,Modelo)
    e=catalogo["respostas_especificas"][0]
    e["pergunta"]="Pergunta cuja redação não aparece no formulário"
    monkeypatch.setattr("minerva_dataset.entrada_contextual",lambda q:e)
    monkeypatch.setattr(rag,"_buscar_lexico",lambda *a,**kw:[])
    monkeypatch.setattr(rag,"_buscar_semantico",lambda *a,**kw:[])
    fontes=rag.buscar_em_documentos_postgres(banco,"Alias exato")
    assert len(fontes)==1 and fontes[0]["fonte"]=="Páginas do contexto documental cadastrado"
    monkeypatch.setattr("minerva_dataset.entrada_contextual",lambda q:None)
    assert rag.buscar_em_documentos_postgres(banco,"Pergunta genérica")==[]


def test_falha_de_banco_no_contexto_nao_publica_resposta(monkeypatch,catalogo):
    import minerva_hybrid as rag
    monkeypatch.setattr("minerva_dataset.entrada_contextual",lambda q:catalogo["respostas_especificas"][0])
    monkeypatch.setattr(rag,"_buscar_lexico",lambda *a,**kw:[])
    monkeypatch.setattr(rag,"_buscar_semantico",lambda *a,**kw:[])
    class Quebrada:
        def cursor(self):
            raise RuntimeError("Banco indisponível")
    assert rag.buscar_em_documentos_postgres(Quebrada(),"Alias exato")==[]
