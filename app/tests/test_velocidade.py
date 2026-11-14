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


# ------------------------------------------------- ajustes de 12/11 (noite)

import minerva_dataset as md  # noqa: E402

ALIAS = "Quanto tempo dura a defesa de TCC na Resolução FCT 01/2012?"


@pytest.mark.parametrize("pergunta", [
    "Minerva, " + ALIAS,
    "Oi Minerva! " + ALIAS + " Obrigado",
    "Boa noite, por favor: " + ALIAS,
    "Eu queria saber " + ALIAS.lower(),
])
def test_cortesia_nas_pontas_nao_impede_o_catalogo(pergunta):
    assert md.entrada_contextual(pergunta)["id"] == md.entrada_contextual(ALIAS)["id"]


@pytest.mark.parametrize("pergunta", [
    "Minerva", "boa noite", "Minerva qual é a função do item VIII?",
    "Minerva, quanto tempo dura a defesa?",
])
def test_cortesia_nao_cria_contexto_implicito(pergunta):
    assert md.entrada_contextual(pergunta) is None


def test_nenhum_alias_do_catalogo_depende_da_remocao_de_cortesia():
    for e in md._carregar_entradas():
        if not e.get("contexto_documental"):
            continue  # só o catálogo contextual usa as variantes
        for q in [e["pergunta"], *e.get("variacoes", [])]:
            assert md._variantes_pergunta(md._norm(q)) == [md._norm(q)], q


def test_catalogo_relido_so_quando_o_arquivo_muda(tmp_path, monkeypatch):
    arq = tmp_path / "d.json"
    arq.write_text('{"respostas_especificas": [{"id": "A"}]}')
    monkeypatch.setattr(md, "DATASET_PATH", arq)
    monkeypatch.setattr(md, "_CACHE_DATASET", {"assinatura": None, "entradas": []})
    leituras = []
    original = type(arq).read_text

    def contar(self, *a, **k):
        leituras.append(self)
        return original(self, *a, **k)

    monkeypatch.setattr(type(arq), "read_text", contar)
    assert [e["id"] for e in md._carregar_entradas()] == ["A"]
    md._carregar_entradas()
    assert len(leituras) == 1
    import os
    arq.write_text('{"respostas_especificas": [{"id": "B"}, {"id": "C"}]}')
    os.utime(arq, ns=(1, 10**18))
    assert [e["id"] for e in md._carregar_entradas()] == ["B", "C"]
    assert len(leituras) == 2


def test_seletor_normativo_pede_resposta_curta(monkeypatch):
    fontes = _fontes()
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a, **k: fontes)
    monkeypatch.setattr(rag, "_entrada_contextual", lambda pergunta: None)
    pedidos = []

    def llm(prompt, max_tokens=None):
        pedidos.append(max_tokens)
        return '{"ids":[1]}'

    rag.responder_minerva("Qual a regra do TCC na resolução?", llm_func=llm)
    assert pedidos == [rag.MAX_TOKENS_SELECAO]


def test_chamar_llm_aceita_funcao_sem_opcoes():
    assert rag._chamar_llm(lambda p: p.upper(), "ok", max_tokens=10) == "OK"


# --------------------------------------- perguntas simuladas (13/11/2026)

import minerva_priority_router as router  # noqa: E402


@pytest.mark.parametrize("pergunta", [
    "o tcc precisa ter quantas paginas",
    "quanto tempo eu tenho pra apresentar o tcc na banca?",
    "qual nota minima pra passar em tcc 2",
    "depois da defesa tenho quantos dias pra corrigir o tcc",
    "estagio de quantas horas no minimo na eng da computacao",
    "posso usar estagio como atividade complementar?",
    "o professor tem prazo pra lançar nota?",
    "o professor tem que colocar o plano da disciplina na internet?",
    "qnt tempo dura a defeza do tcc",
])
def test_detalhe_normativo_vai_para_documentos(pergunta):
    assert router.classify_question(pergunta) is None
    assert router.priority_answer(pergunta) is None


@pytest.mark.parametrize("pergunta, rota", [
    ("Quais são as regras de estágio?", "internship"),
    ("Quero saber o regulamento do TCC", "tcc"),
    ("Quantos membros deve ter a banca do TCC?", "tcc_board"),
    ("Quem são os professores da FCT?", "faculty"),
    ("Como faço para integralizar atividades complementares?", "atividades_complementares"),
    ("quero aproveitar disciplina de outra faculdade", "aproveitamento_estudos"),
])
def test_rotas_gerais_continuam(pergunta, rota):
    assert router.classify_question(pergunta) == rota


@pytest.mark.parametrize("pergunta", [
    "como funciona o tcc na usp?", "regras de estágio da UNICAMP", "a uepa tem segunda chamada?",
])
def test_siglas_externas_sao_barradas(pergunta):
    from prompts import pergunta_menciona_instituicao_externa
    assert pergunta_menciona_instituicao_externa(pergunta)



def test_siglas_externas_sem_falso_positivo():
    from prompts import pergunta_menciona_instituicao_externa
    for pergunta in ("como faço o tcc?", "qual o prazo da ufpa?", "usuario do sigaa"):
        assert not pergunta_menciona_instituicao_externa(pergunta), pergunta


def test_barreira_externa_vem_antes_das_rotas_fixas(monkeypatch):
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_processar_pergunta")
    src = ast.get_source_segment((Path(__file__).parents[1] / "main.py").read_text(), func)
    assert src.index("pergunta_menciona_instituicao_externa(pergunta)") < src.index("priority_answer(pergunta)")


def test_cortesia_informal_no_fim():
    assert md.entrada_contextual("Como cancelar uma chamada aberta no SAGITTA? valeu") is not None


def test_entradas_de_exercicio_domiciliar_inativas_ate_radip():
    por_id = {e["id"]: e for e in md._carregar_entradas()}
    for i in ("MINERVA_0104", "MINERVA_0105"):
        assert por_id[i]["ativo"] is False and "5.799/2024" in por_id[i]["motivo_inativacao"]


def test_avaliacao_simulada_le_citacoes_e_pontua():
    from scripts import avaliar_simuladas as av
    resp = ("Trechos...\nResolucao_TCC.pdf · página física 5 · [T:1]\n"
            "Regulamento_Graduacao.pdf · páginas físicas 27–28 · [T:2]")
    assert av.citacoes(resp) == [("Resolucao_TCC.pdf", 5), ("Regulamento_Graduacao.pdf", 27),
                                 ("Regulamento_Graduacao.pdf", 28)]
    caso = {"esperado": {"tipo": "documental", "documento": "Regulamento_Graduacao.pdf", "paginas": [28]}}
    assert av.avaliar(caso, resp, "rag_generico", "FB")["ok"]
    assert not av.avaliar({"esperado": {"tipo": "abstencao"}}, resp, "rag_generico", "FB")["ok"]
    assert av.avaliar({"esperado": {"tipo": "abstencao"}}, "FB", "rag_generico", "FB")["ok"]
    linhas = [{"id": "S1", "estilo": "x", "pergunta": "q", "rota": "rag_generico", "ms": 100,
               "esperado": {**caso["esperado"], "entrada": "MINERVA_0115"},
               "avaliacao": av.avaliar(caso, resp, "rag_generico", "FB")}]
    assert av.resumir(linhas)["sugestoes_variacoes_catalogo"][0]["entrada"] == "MINERVA_0115"


def test_perguntas_simuladas_sao_validas():
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).parent / "data" / "perguntas_simuladas_20261113.json").read_text())
    ids = [p["id"] for p in d["perguntas"]]
    assert len(ids) == len(set(ids)) == d["total"]
    por_id = {e["id"]: e for e in md._carregar_entradas()}
    for p in d["perguntas"]:
        e = p["esperado"].get("entrada")
        if e:
            assert por_id[e]["ativo"] is not False, p["id"]


# ---------------------------------------------------------------------------
# Catálogo: complementa com trechos das páginas cadastradas (caso 0150)
# ---------------------------------------------------------------------------
import minerva_dataset as _md  # noqa: E402


def _item(i):
    return {"id": i, "titulo": "IN_05_2023_PROEG_TrabalhoDeCurso.pdf",
            "trecho": f"trecho {i}", "pagina_inicio": 4, "pagina_fim": 4}


def _cenario_escopo(monkeypatch, lexico, semantico, escopo_ids):
    entrada = {"pergunta": "Quem pode orientar?", "contexto_documental": {
        "documento": "IN_05_2023_PROEG_TrabalhoDeCurso.pdf",
        "documento_sha256": "x" * 64, "paginas_fisicas": [4]}}
    monkeypatch.setattr(_md, "entrada_contextual", lambda p: entrada)
    monkeypatch.setattr(rag, "_buscar_lexico", lambda *a, **k: [_item(i) for i in lexico])
    monkeypatch.setattr(rag, "_buscar_semantico", lambda *a, **k: [_item(i) for i in semantico])
    chamadas = []

    def escopo(conn, esc, limite):
        chamadas.append(esc["paginas_fisicas"])
        return [_item(i) for i in escopo_ids]
    monkeypatch.setattr(rag, "_trechos_do_escopo", escopo)
    return chamadas


def test_catalogo_completa_com_trechos_das_paginas_cadastradas(monkeypatch):
    _cenario_escopo(monkeypatch, [558], [], [557, 558, 559])
    ids = [f["id"] for f in rag.buscar_em_documentos_postgres(object(), "x")]
    assert ids == [558, 557, 559]  # o ranqueado primeiro, depois as páginas


def test_catalogo_com_tres_trechos_nao_consulta_escopo(monkeypatch):
    chamadas = _cenario_escopo(monkeypatch, [1, 2, 3], [3, 4], [9])
    ids = [f["id"] for f in rag.buscar_em_documentos_postgres(object(), "x")]
    assert chamadas == [] and 9 not in ids


def test_pergunta_livre_nunca_recebe_complemento(monkeypatch):
    chamadas = _cenario_escopo(monkeypatch, [1], [], [9])
    monkeypatch.setattr(_md, "entrada_contextual", lambda p: None)
    ids = [f["id"] for f in rag.buscar_em_documentos_postgres(object(), "x")]
    assert ids == [1] and chamadas == []


# ---------------------------------------------------------------------------
# Níveis de ensino liberados por entrada do catálogo (caso 0150)
# ---------------------------------------------------------------------------
import copy as _copy  # noqa: E402
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from minerva_normas import filtrar_contexto_normativo  # noqa: E402

_ORIENTADOR = {"id": 1, "titulo": "IN.pdf", "trecho": (
    "§ 2º O(A) orientador(a) será o(a) docente efetivo(a), substituto(a), "
    "professor(a) visitante, pós-doutorando(a) ou discente de doutorado")}


def test_nivel_nao_pedido_continua_filtrado_por_padrao():
    assert filtrar_contexto_normativo("Quem pode orientar o TCC?", [_ORIENTADOR]) == []


def test_nivel_liberado_pela_entrada_mantem_o_trecho():
    assert filtrar_contexto_normativo("Quem pode orientar o TCC?", [_ORIENTADOR],
                                      niveis_permitidos=("doutorado",)) == [_ORIENTADOR]


def test_liberar_doutorado_nao_libera_mestrado():
    fonte = dict(_ORIENTADOR, trecho="regras do curso de mestrado")
    assert filtrar_contexto_normativo("Quem pode orientar?", [fonte],
                                      niveis_permitidos=("doutorado",)) == []


def _dataset():
    return _json.loads((_Path(__file__).parents[1] / "minerva_dataset.json").read_text())


def test_entrada_0150_libera_doutorado_com_justificativa():
    e = [x for x in _dataset()["respostas_especificas"] if x["id"] == "MINERVA_0150"][0]
    c = e["contexto_documental"]
    assert c["niveis_permitidos"] == ["doutorado"] and c["niveis_permitidos_justificativa"]


@pytest.mark.parametrize("niveis,just", [(["doutorado"], ""), (["graduacao"], "x")])
def test_validacao_rejeita_nivel_sem_justificativa_ou_desconhecido(niveis, just):
    from minerva_qa_catalogo import validar_dataset
    d = _dataset()
    e = [x for x in d["respostas_especificas"] if x["id"] == "MINERVA_0150"][0]
    e["contexto_documental"]["niveis_permitidos"] = niveis
    e["contexto_documental"]["niveis_permitidos_justificativa"] = just
    with pytest.raises(ValueError, match="Níveis permitidos"):
        validar_dataset(_copy.deepcopy(d))


def test_resposta_contextual_usa_niveis_da_entrada(monkeypatch):
    entrada = {"contexto_documental": {"niveis_permitidos": ["doutorado"]}}
    monkeypatch.setattr(rag, "_entrada_contextual", lambda p: entrada)
    resposta = rag.resposta_contextual("Quem pode orientar o TCC na IN 05/2023?",
                                       [dict(_ORIENTADOR, id=558, titulo="IN_05.pdf")])
    assert "discente de doutorado" in resposta
