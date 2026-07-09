from prompts import (
    pergunta_menciona_instituicao_externa,
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
