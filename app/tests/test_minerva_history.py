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
    assert msg["role"] == "assistant"
    assert msg["content"] == "Olá"


def test_normalizar_dict_preserva_chaves_extras():
    # Bug real: dict de entrada com chaves além de role/content (ex.:
    # historico_id, feedback, download_file — ver main.py/ui.py) perdia
    # tudo, porque a função sempre devolvia um literal novo só com
    # role/content. normalizar_lista_mensagens() chama esta função a cada
    # rerun do Streamlit (via normalizar_historico_session_state), então
    # isso apagava dado real da sessão em uso, não só de histórico salvo.
    msg = normalizar_mensagem_historico(
        {"role": "assistant", "content": "Olá", "historico_id": 42, "feedback": None}
    )
    assert msg == {
        "role": "assistant",
        "content": "Olá",
        "historico_id": 42,
        "feedback": None,
    }


def test_normalizar_string_nao_ganha_chaves_extras():
    # Só dict de entrada preserva chaves extras — string/tupla/None não
    # têm de onde herdar nada além de role/content.
    msg = normalizar_mensagem_historico("Olá", role_padrao="assistant")
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
