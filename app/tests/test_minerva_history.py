from minerva_history import (
    mensagem_content,
    mensagem_role,
    normalizar_lista_mensagens,
    normalizar_mensagem_historico,
)


def test_normalizar_dict_padrao():
    msg = normalizar_mensagem_historico({"role": "user", "content": "Oi"})
    assert msg == {"role": "user", "content": "Oi"}


def test_normalizar_dict_chaves_alternativas():
    msg = normalizar_mensagem_historico({"tipo": "assistente", "resposta": "Olá"})
    assert msg == {"role": "assistant", "content": "Olá"}


def test_normalizar_string_usa_role_padrao():
    msg = normalizar_mensagem_historico("Resposta antiga", role_padrao="assistant")
    assert msg == {"role": "assistant", "content": "Resposta antiga"}


def test_normalizar_tupla():
    msg = normalizar_mensagem_historico(("user", "Pergunta"))
    assert msg == {"role": "user", "content": "Pergunta"}


def test_normalizar_none():
    msg = normalizar_mensagem_historico(None, role_padrao="system")
    assert msg == {"role": "system", "content": ""}


def test_normalizar_objeto_com_atributos():
    class Msg:
        role = "minerva"
        content = "Resposta via objeto"

    msg = normalizar_mensagem_historico(Msg())
    assert msg == {"role": "assistant", "content": "Resposta via objeto"}


def test_normalizar_role_desconhecida_cai_no_padrao():
    msg = normalizar_mensagem_historico({"role": "robo", "content": "x"}, role_padrao="assistant")
    assert msg["role"] == "assistant"


def test_normalizar_lista_mensagens_historico_misto():
    # Formato antigo: string "solta" sem role, alternando com dicts.
    entrada = [
        {"role": "user", "content": "Pergunta"},
        "Resposta da Minerva",
        "Segunda pergunta",
    ]
    resultado = normalizar_lista_mensagens(entrada)

    assert resultado == [
        {"role": "user", "content": "Pergunta"},
        {"role": "assistant", "content": "Resposta da Minerva"},
        {"role": "user", "content": "Segunda pergunta"},
    ]


def test_normalizar_lista_mensagens_vazia_ou_none():
    assert normalizar_lista_mensagens(None) == []
    assert normalizar_lista_mensagens([]) == []


def test_normalizar_lista_mensagens_ignora_conteudo_vazio():
    resultado = normalizar_lista_mensagens([{"role": "user", "content": "   "}])
    assert resultado == []


def test_mensagem_role_e_content_sem_assumir_dict():
    assert mensagem_role("texto solto", default="user") == "user"
    assert mensagem_content("texto solto") == "texto solto"
