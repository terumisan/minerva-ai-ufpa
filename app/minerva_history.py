from __future__ import annotations

# ======================================================================
# MINERVA AI
#
# Normalização de histórico de conversa: funções puras (sem dependência de
# Streamlit) extraídas de main.py para poderem ser testadas isoladamente.
# ======================================================================


def normalizar_mensagem_historico(msg, role_padrao="assistant"):
    """
    Converte qualquer formato antigo ou novo para:

    {
        "role": "user|assistant|system",
        "content": "texto"
    }

    Compatível com:
    - dict
    - str
    - tuple
    - list
    - objetos com role/content
    """

    role = role_padrao
    content = ""

    if isinstance(msg, dict):

        role = (
            msg.get("role")
            or msg.get("tipo")
            or msg.get("sender")
            or msg.get("autor")
            or role_padrao
        )

        if msg.get("content") is not None:
            content = msg.get("content")

        elif msg.get("conteudo") is not None:
            content = msg.get("conteudo")

        elif msg.get("message") is not None:
            content = msg.get("message")

        elif msg.get("text") is not None:
            content = msg.get("text")

        elif msg.get("resposta") is not None:
            content = msg.get("resposta")

        else:
            content = ""

    elif isinstance(msg, (tuple, list)) and len(msg) >= 2:

        role = msg[0] or role_padrao
        content = msg[1]

    elif isinstance(msg, str):

        role = role_padrao
        content = msg

    elif msg is None:

        role = role_padrao
        content = ""

    else:

        role_obj = getattr(
            msg,
            "role",
            None
        )

        content_obj = getattr(
            msg,
            "content",
            None
        )

        if role_obj is not None:
            role = role_obj

        if content_obj is not None:
            content = content_obj

        else:
            content = str(msg)


    role = str(
        role or role_padrao
    ).strip().lower()


    aliases = {

        "usuario": "user",
        "usuário": "user",
        "human": "user",
        "pergunta": "user",
        "cliente": "user",

        "assistente": "assistant",
        "bot": "assistant",
        "ai": "assistant",
        "ia": "assistant",
        "minerva": "assistant",
        "resposta": "assistant",
    }


    role = aliases.get(
        role,
        role
    )


    if role not in {
        "user",
        "assistant",
        "system"
    }:

        role = (
            role_padrao
            if role_padrao in {
                "user",
                "assistant",
                "system"
            }
            else "assistant"
        )


    return {
        "role": role,
        "content": str(content or "")
    }



def normalizar_lista_mensagens(messages):
    """
    Corrige históricos mistos.

    Exemplo antigo:

    [
        {"role": "user", "content": "Pergunta"},
        "Resposta da Minerva"
    ]

    Resultado:

    [
        {"role": "user", "content": "Pergunta"},
        {"role": "assistant", "content": "Resposta da Minerva"}
    ]
    """

    if messages is None:
        return []


    if isinstance(
        messages,
        (str, dict)
    ):
        messages = [messages]


    try:
        itens = list(messages)

    except Exception:
        itens = [messages]


    resultado = []
    ultimo_role = None


    for item in itens:

        if isinstance(item, dict):

            role_existente = item.get(
                "role"
            )

            if role_existente:
                role_padrao = str(
                    role_existente
                ).lower()

            elif ultimo_role == "user":
                role_padrao = "assistant"

            elif ultimo_role == "assistant":
                role_padrao = "user"

            else:
                role_padrao = "assistant"

        else:

            if ultimo_role == "user":
                role_padrao = "assistant"

            elif ultimo_role == "assistant":
                role_padrao = "user"

            else:
                role_padrao = "assistant"


        msg = normalizar_mensagem_historico(
            item,
            role_padrao=role_padrao
        )


        if msg["content"].strip():

            resultado.append(
                msg
            )

            ultimo_role = msg["role"]


    return resultado



def mensagem_role(msg, default="assistant"):
    """
    Retorna role sem assumir que msg seja dict.
    """

    return normalizar_mensagem_historico(
        msg,
        role_padrao=default
    )["role"]



def mensagem_content(msg, default=""):
    """
    Retorna content sem assumir que msg seja dict.
    """

    resultado = normalizar_mensagem_historico(
        msg
    )["content"]

    if resultado is None:
        return default

    return str(resultado)


__all__ = [
    "normalizar_mensagem_historico",
    "normalizar_lista_mensagens",
    "mensagem_role",
    "mensagem_content",
]
