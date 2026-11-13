"""Caminho sem LLM para perguntas do catálogo e cache de respostas repetidas."""
import pytest

import minerva_cache as mc
import minerva_hybrid as rag

ENTRADA = {"id": "MINERVA_TESTE", "contexto_documental": {"documento": "a.pdf"}}


def _fontes():
    return [
        {"id": 1, "titulo": "Resolucao_TCC.pdf", "trecho": "Art. 16 - A duração da defesa é de no máximo 60 minutos."},
        {"id": 2, "titulo": "Resolucao_TCC.pdf", "trecho": "Art. 15 - O número mínimo de páginas do TCC é 35."},
        {"id": 3, "titulo": "Resolucao_TCC.pdf", "trecho": "Art. 14 - Aprovado com conceito mínimo REGULAR."},
        {"id": 4, "titulo": "Resolucao_TCC.pdf", "trecho": "Art. 17 - Cópia digital para cada membro da banca."},
    ]


def _sem_llm(_prompt):
    pytest.fail("Pergunta do catálogo não deve chamar o modelo")


@pytest.fixture
def contextual(monkeypatch):
    fontes = _fontes()
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a, **k: fontes)
    monkeypatch.setattr(rag, "_entrada_contextual", lambda pergunta: ENTRADA)
    return fontes


def test_catalogo_responde_sem_llm_com_os_primeiros_trechos(contextual):
    resposta = rag.responder_minerva("Quanto tempo dura a defesa?", llm_func=_sem_llm)
    assert resposta.startswith(rag.TEXTO_EXCERTOS)
    for i in (1, 2, 3):
        assert f"[T:{i}]" in resposta
    assert "[T:4]" not in resposta


def test_catalogo_mantem_ressalva_do_mesmo_documento(contextual):
    contextual[3]["trecho"] = "Art. 17 - Prazo de 10 dias, salvo decisão da banca."
    resposta = rag.responder_minerva("Quanto tempo dura a defesa?", llm_func=_sem_llm)
    assert "[T:4]" in resposta


def test_catalogo_descarta_nivel_de_ensino_nao_pedido(contextual):
    contextual[0]["trecho"] = "Na especialização, a defesa dura 90 minutos."
    resposta = rag.responder_minerva("Quanto tempo dura a defesa?", llm_func=_sem_llm)
    assert "[T:1]" not in resposta and "[T:2]" in resposta


def test_catalogo_preserva_barreira_de_abandono(contextual):
    resposta = rag.responder_minerva("Se eu abandonar o curso perco a vaga?", llm_func=_sem_llm)
    assert resposta == rag.fallback_sem_base()


def test_sem_trechos_no_catalogo_segue_fluxo_normal(monkeypatch):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a, **k: [])
    monkeypatch.setattr(rag, "_entrada_contextual", lambda pergunta: ENTRADA)
    assert rag.responder_minerva("Pergunta?", llm_func=_sem_llm) == rag.fallback_sem_base()


def test_pergunta_fora_do_catalogo_ainda_usa_o_modelo(monkeypatch):
    fontes = _fontes()
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a, **k: fontes)
    monkeypatch.setattr(rag, "_entrada_contextual", lambda pergunta: None)
    chamadas = []

    def llm(prompt):
        chamadas.append(prompt)
        return '{"ids":[2]}'

    resposta = rag.responder_minerva("Qual a regra do TCC na resolução?", llm_func=llm)
    assert chamadas and "[T:2]" in resposta


def test_alias_real_do_catalogo_e_reconhecido():
    entrada = rag._entrada_contextual("Quanto tempo dura a defesa de TCC na Resolução FCT 01/2012?")
    assert entrada is not None and entrada["contexto_documental"]["documento"] == "Resolucao_TCC.pdf"


# ---------------------------------------------------------------- cache


class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_cache_acerta_mesma_pergunta_normalizada():
    c = mc.CacheRespostas(capacidade=4, ttl=60)
    c.guardar("Quanto dura a defesa?", "v1", "resposta")
    assert c.obter("quanto DURA a defesa", "v1") == "resposta"


def test_cache_invalida_quando_versao_muda():
    c = mc.CacheRespostas(capacidade=4, ttl=60)
    c.guardar("Pergunta", "v1", "antiga")
    assert c.obter("Pergunta", "v2") is None


def test_cache_expira_pelo_ttl():
    r = Relogio()
    c = mc.CacheRespostas(capacidade=4, ttl=10, relogio=r)
    c.guardar("Pergunta", "v1", "resposta")
    r.t = 11
    assert c.obter("Pergunta", "v1") is None and len(c) == 0


def test_cache_descarta_o_menos_usado():
    c = mc.CacheRespostas(capacidade=2, ttl=60)
    c.guardar("a", "v", "A")
    c.guardar("b", "v", "B")
    c.obter("a", "v")
    c.guardar("c", "v", "C")
    assert c.obter("b", "v") is None and c.obter("a", "v") == "A"


def test_cache_desligado_sem_versao():
    c = mc.CacheRespostas(capacidade=4, ttl=60)
    c.guardar("Pergunta", "", "resposta")
    assert c.obter("Pergunta", "") is None and len(c) == 0


def test_so_guarda_resposta_documental():
    falhas = (rag.fallback_sem_base(), "Com base nas fontes institucionais disponíveis")
    assert mc.resposta_cacheavel(rag.TEXTO_EXCERTOS + "...", falhas)
    assert not mc.resposta_cacheavel(rag.fallback_sem_base(), falhas)
    assert not mc.resposta_cacheavel("Com base nas fontes institucionais disponíveis da FCT/UFPA:\n...", falhas)
    assert not mc.resposta_cacheavel("", falhas)
    assert not mc.resposta_cacheavel(None, falhas)


class _Cursor:
    def __init__(self, valor, erro=False):
        self.valor, self.erro = valor, erro

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a):
        if self.erro:
            raise RuntimeError("sem tabela")

    def fetchone(self):
        return (self.valor,)


class _Conn:
    def __init__(self, valor, erro=False):
        self.valor, self.erro, self.rollbacks = valor, erro, 0

    def cursor(self):
        return _Cursor(self.valor, self.erro)

    def rollback(self):
        self.rollbacks += 1


def test_versao_muda_com_corpus_e_dataset(tmp_path):
    ds = tmp_path / "d.json"
    ds.write_text("{}")
    v1 = mc.versao_base(_Conn("a.pdf:h1"), ds)
    assert v1 and v1 == mc.versao_base(_Conn("a.pdf:h1"), ds)
    assert v1 != mc.versao_base(_Conn("a.pdf:h2"), ds)
    ds.write_text('{"x": 1}')
    assert v1 != mc.versao_base(_Conn("a.pdf:h1"), ds)


def test_versao_vazia_sem_banco_ou_com_erro(tmp_path):
    ds = tmp_path / "d.json"
    ds.write_text("{}")
    assert mc.versao_base(None, ds) == ""
    conn = _Conn("", erro=True)
    assert mc.versao_base(conn, ds) == "" and conn.rollbacks == 1


def _processar_da_ui(monkeypatch, responder, cache, versao="v"):
    """Executa _processar_pergunta do main.py com dependências controladas."""
    import ast
    from pathlib import Path
    from types import SimpleNamespace

    tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_processar_pergunta"]

    class Pool:
        def getconn(self):
            return SimpleNamespace(rollback=lambda: None)

        def putconn(self, conn, close=False):
            pass

    ns = {
        "priority_answer": lambda p: None,
        "pergunta_menciona_instituicao_externa": lambda p: False,
        "db_pool": Pool(), "consultar_modelo_local": lambda p: pytest.fail("sem LLM"),
        "responder_minerva": responder, "fallback_sem_base": rag.fallback_sem_base,
        "CACHE": cache, "versao_base": lambda conn: versao,
        "resposta_cacheavel": mc.resposta_cacheavel,
    }
    exec(compile(ast.Module(body=funcs, type_ignores=[]), "main.py", "exec"), ns)
    return ns["_processar_pergunta"]


def test_ui_repete_resposta_pelo_cache(monkeypatch):
    chamadas = []

    def responder(**kw):
        chamadas.append(kw["pergunta"])
        return rag.TEXTO_EXCERTOS + " [T:1]"

    cache = mc.CacheRespostas(capacidade=8, ttl=60)
    processar = _processar_da_ui(monkeypatch, responder, cache)
    assert processar("Quanto dura a defesa?")[1] == "rag_generico"
    resposta, rota = processar("quanto dura a defesa")
    assert rota == "rag_cache" and resposta.endswith("[T:1]") and len(chamadas) == 1


def test_ui_nao_guarda_fallback(monkeypatch):
    chamadas = []

    def responder(**kw):
        chamadas.append(1)
        return rag.fallback_sem_base()

    processar = _processar_da_ui(monkeypatch, responder, mc.CacheRespostas(capacidade=8, ttl=60))
    processar("Pergunta sem base")
    assert processar("Pergunta sem base")[1] == "rag_generico" and len(chamadas) == 2
