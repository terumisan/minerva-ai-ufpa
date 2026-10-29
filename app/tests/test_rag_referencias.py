import pytest

import minerva_hybrid as rag


@pytest.fixture
def fontes():
    return [
        {"id": 17, "titulo": "Regimento.pdf", "trecho": "O colegiado avalia os projetos."},
        {"id": 28, "titulo": "Calendario.pdf", "trecho": "As aulas começam em março."},
    ]


def test_rrf_preserva_id_e_documento(fontes):
    resultado = rag._fusao_rrf(fontes, list(reversed(fontes)))
    assert {f["id"]: f["titulo"] for f in resultado} == {
        17: "Regimento.pdf", 28: "Calendario.pdf"
    }


def test_referencia_valida_lista_apenas_trecho_citado(monkeypatch, fontes):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: fontes)

    def llm(prompt):
        assert "[T:17] Documento: Regimento.pdf" in prompt
        assert "[T:28] Documento: Calendario.pdf" in prompt
        return "O colegiado avalia os projetos [T:17]. Outra menção [T:17]."

    resposta = rag.responder_minerva("Atribuições?", llm_func=llm)
    assert "Documento: `Regimento.pdf`" in resposta
    assert "O colegiado avalia os projetos." in resposta
    assert "Calendario.pdf" not in resposta
    assert "https://" not in resposta
    assert resposta.count("Documento:") == 1
    assert rag.validar_referencias("Resposta [T:28] e [T:17] e [T:28].", fontes) == [28, 17]


@pytest.mark.parametrize("texto", [
    "Afirmação [T:999].", "Afirmação [T:17] e [T:999].",
    "Afirmação sem referência.", "", None,
    "Afirmação [T:abc].", "Afirmação [T:17] e [99].",
    "Afirmação [T:17", "Afirmação [T:017].",
    "Afirmação [T:17]. https://ufpa.br/inventado",
    "Afirmação [T:17]. www.exemplo.com",
])
def test_referencia_invalida_nao_publica_geracao(monkeypatch, fontes, texto):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: fontes)
    assert rag.validar_referencias(texto, fontes) is None
    assert rag.responder_minerva("Pergunta?", llm_func=lambda p: texto) == rag.fallback_sem_base()


def test_sem_evidencia_nao_chama_llm(monkeypatch):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: [])
    def llm(prompt):
        pytest.fail("Não deve gerar sem evidência")
    assert rag.responder_minerva("Pergunta?", llm_func=llm) == rag.fallback_sem_base()
    assert rag.validar_referencias("Resposta [T:17].", []) is None


def test_contexto_sem_id_ou_documento_nao_autoriza(monkeypatch):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: [
        {"titulo": "SemId.pdf", "trecho": "Texto"},
        {"id": 17, "trecho": "Sem documento"},
    ])
    assert rag.responder_minerva("Pergunta?") == rag.fallback_sem_base()


def test_id_ambiguo_nao_autoriza(fontes):
    fontes.append({"id": 17, "titulo": "Outro.pdf", "trecho": "Outro texto"})
    assert rag.validar_referencias("Resposta [T:17].", fontes) is None


def test_fallback_extrativo_referencia_somente_textos_exibidos(fontes):
    fontes += [{"id": i, "titulo": f"Doc{i}.pdf", "trecho": f"Texto {i}"} for i in (30, 40)]
    resposta = rag.resposta_extrativa(fontes)
    assert "[T:17]" in resposta and "[T:28]" in resposta and "[T:30]" in resposta
    assert "[T:40]" not in resposta and "Doc40.pdf" not in resposta


def test_erro_llm_preserva_fallback_rastreavel(monkeypatch, fontes):
    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: fontes)
    def llm(prompt):
        raise RuntimeError("LLM indisponível")
    resposta = rag.responder_minerva("Pergunta?", llm_func=llm)
    assert "Documento: `Regimento.pdf`" in resposta
    assert "[T:17]" in resposta


def test_fluxo_da_ui_nao_exibe_referencia_invalida_antes_de_validar(monkeypatch, fontes):
    import ast
    from pathlib import Path

    monkeypatch.setattr(rag, "buscar_em_documentos_postgres", lambda *a: fontes)
    tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "processar_pergunta")

    class Pool:
        returned = False
        def getconn(self):
            return object()
        def putconn(self, conn):
            self.returned = True

    class Area:
        def markdown(self, text):
            pytest.fail("A UI não pode mostrar texto antes da validação")

    pool = Pool()
    def llm(prompt, **kwargs):
        assert "on_chunk" not in kwargs
        return "Resposta inventada [T:999]."

    namespace = {
        "priority_answer": lambda p: None,
        "pergunta_menciona_instituicao_externa": lambda p: False,
        "db_pool": pool, "consultar_modelo_local": llm,
        "responder_minerva": rag.responder_minerva,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), namespace)
    answer, route = namespace["processar_pergunta"]("Pergunta?", stream_area=Area())
    assert answer == rag.fallback_sem_base()
    assert route == "rag_generico"
    assert pool.returned
