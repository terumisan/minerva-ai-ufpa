from prompts import (
    _extrair_delta_sse,
    _texto_sem_palavra_incompleta,
    pergunta_menciona_instituicao_externa,
    resposta_viola_escopo,
    validar_resposta_institucional,
)


def test_pergunta_menciona_instituicao_externa_fct_portugal():
    assert pergunta_menciona_instituicao_externa("O que é a FCT de Portugal?")


def test_pergunta_menciona_instituicao_externa_universidade_nova_de_lisboa():
    assert pergunta_menciona_instituicao_externa(
        "Me fale sobre a Universidade Nova de Lisboa"
    )


def test_pergunta_menciona_instituicao_externa_faculdade_ciencias_tecnologia():
    assert pergunta_menciona_instituicao_externa(
        "Qual a diferença entre a FCT do Brasil e a Faculdade de Ciências e Tecnologia?"
    )


def test_pergunta_menciona_instituicao_externa_fct_unl():
    assert pergunta_menciona_instituicao_externa("A FCT-UNL fica onde?")


def test_pergunta_sem_mencao_externa_nao_bloqueia():
    assert not pergunta_menciona_instituicao_externa(
        "Quais são as regras de estágio da FCT?"
    )


def test_validar_resposta_bloqueia_universidade_nova_de_lisboa():
    # Bug real: esta função não tinha nenhuma entrada relacionada a Portugal
    # (nem "Faculdade de Ciências e Tecnologia" nem "Universidade Nova de
    # Lisboa") — uma resposta do modelo mencionando essa instituição
    # passava direto por aqui, restando só a barreira final (sanitizar_
    # resposta, em minerva_hybrid.py) como última linha de defesa.
    resposta = validar_resposta_institucional(
        "A FCT significa Faculdade de Ciências e Tecnologia, da Universidade Nova de Lisboa."
    )
    assert "Referência institucional correta" in resposta


def test_validar_resposta_bloqueia_universidade_nova_de_lisboa_isolada():
    resposta = validar_resposta_institucional(
        "Trata-se da Universidade Nova de Lisboa, em Portugal."
    )
    assert "Referência institucional correta" in resposta


def test_validar_resposta_bloqueia_fct_de_portugal_sem_nome_completo():
    resposta = validar_resposta_institucional(
        "A FCT de Portugal fica em Lisboa e é uma instituição pública."
    )
    assert "Referência institucional correta" in resposta


def test_validar_resposta_bloqueia_fct_unl():
    resposta = validar_resposta_institucional("A FCT-UNL é uma faculdade portuguesa.")
    assert "Referência institucional correta" in resposta


def test_validar_resposta_sem_mencao_externa_passa_direto():
    resposta = "O regulamento de estágio exige carga horária mínima definida pela FCT."
    assert validar_resposta_institucional(resposta) == resposta


# ----------------------------------------------------------------------
# Streaming (SSE) e barreira incremental
# ----------------------------------------------------------------------

def test_extrair_delta_sse_linha_de_conteudo():
    linha = 'data: {"choices": [{"delta": {"content": "Olá"}}]}'
    assert _extrair_delta_sse(linha) == "Olá"


def test_extrair_delta_sse_ignora_done_vazio_e_malformado():
    assert _extrair_delta_sse("data: [DONE]") is None
    assert _extrair_delta_sse("") is None
    assert _extrair_delta_sse(None) is None
    assert _extrair_delta_sse("data: {json quebrado") is None
    # Linha que não é evento SSE de dados.
    assert _extrair_delta_sse(": keep-alive") is None


def test_extrair_delta_sse_primeiro_chunk_so_com_role():
    # O primeiro chunk do llama.cpp costuma trazer só o role, sem content —
    # deve virar string vazia (conteúdo neutro), não None (linha inútil),
    # para não ser confundido com fim de stream por quem consome.
    linha = 'data: {"choices": [{"delta": {"role": "assistant"}}]}'
    assert _extrair_delta_sse(linha) == ""


def test_resposta_viola_escopo_classifica_associacao_e_sigla():
    assert resposta_viola_escopo("A FCT fica em Lisboa.") == "associacao"
    assert resposta_viola_escopo("Consulte a UFPE.") == "sigla"
    assert resposta_viola_escopo("A FCT/UFPA fica em Belém do Pará.") is None


def test_texto_sem_palavra_incompleta_evita_falso_positivo_de_sigla():
    # "...a UFP" é a UFPA cortada no meio pelo chunk do streaming — sem o
    # corte da última palavra, "ufp" casaria \bUFxx\b e bloquearia à toa.
    parcial = "Os cursos da UFP"
    assert resposta_viola_escopo(_texto_sem_palavra_incompleta(parcial)) is None
    # Com a palavra completa, segue detectando sigla externa de verdade.
    assert resposta_viola_escopo("Os cursos da UFPE ") == "sigla"
