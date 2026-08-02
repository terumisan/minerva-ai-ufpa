from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import streamlit as st

# MINERVA_UI_HISTORY_IMPORT_BEGIN
try:
    from .minerva_history import (
        normalizar_lista_mensagens,
        mensagem_role,
        mensagem_content,
    )
except (ImportError, ValueError):
    from minerva_history import (
        normalizar_lista_mensagens,
        mensagem_role,
        mensagem_content,
    )
# MINERVA_UI_HISTORY_IMPORT_END

# MINERVA_UI_DB_IMPORT_BEGIN
try:
    from .db import renomear_conversa, excluir_conversa
except (ImportError, ValueError):
    from db import renomear_conversa, excluir_conversa
# MINERVA_UI_DB_IMPORT_END


# ======================================================================
# MINERVA AI
# CSS da interface e componentes de UX: cards de categoria, perguntas
# sugeridas, histórico clicável, downloads e renderização do chat.
# ======================================================================


_TEMA_VARS_CLARO = """
            --minerva-blue: #1E40AF;
            --minerva-blue-soft: #EFF6FF;
            --minerva-border: #E2E8F0;
            --minerva-text: #0F172A;
            --minerva-muted: #64748B;
            --minerva-bg: #F8FAFC;
            --minerva-white: #FFFFFF;
"""

_TEMA_VARS_ESCURO = """
            --minerva-blue: #60A5FA;
            --minerva-blue-soft: rgba(96, 165, 250, 0.16);
            --minerva-border: #334155;
            --minerva-text: #E2E8F0;
            --minerva-muted: #94A3B8;
            --minerva-bg: #0F172A;
            --minerva-white: #1E293B;
"""


def aplicar_css(tema: str = "auto") -> None:
    """Injeta o CSS único da interface.

    Deve ser chamada logo após st.set_page_config(). Bloco único: iterações
    anteriores empilhavam 5 blocos <style> que se sobrepunham (vários deles
    nem miravam mais em classes usadas no HTML atual). Este bloco estiliza
    somente o que existe hoje: as divs ".minerva-v2-*", a sidebar, os
    botões e as mensagens do chat.

    tema: "claro", "escuro" ou "auto" (padrão — segue prefers-color-scheme
    do navegador/SO). Escolha manual do usuário via seletor na sidebar
    (ver main.py, st.session_state["tema_ui"]) tem prioridade sobre a
    preferência do sistema quando não é "auto".
    """
    if tema == "escuro":
        # Sem @media: aplica direto, incondicional — escolha manual vence
        # a preferência do sistema.
        bloco_variaveis = f":root {{{_TEMA_VARS_ESCURO}}}"
    elif tema == "claro":
        bloco_variaveis = f":root {{{_TEMA_VARS_CLARO}}}"
    else:
        # "auto": variáveis claras como base, escuras só dentro do media
        # query — comportamento passivo, segue o SO/navegador.
        bloco_variaveis = f"""
        :root {{{_TEMA_VARS_CLARO}}}

        @media (prefers-color-scheme: dark) {{
            :root {{{_TEMA_VARS_ESCURO}}}
        }}
        """

    # Concatenação, não f-string única: o resto da folha de estilo abaixo
    # é CSS puro cheio de "{" "}" literais — um f-string trataria cada um
    # deles como delimitador de expressão Python e quebraria o parsing.
    # Só o topo (bloco_variaveis, já pré-formatado acima) precisa de
    # interpolação.
    st.markdown(
        "<style>\n" + bloco_variaveis + """

        html, body, .stApp, [data-testid="stAppViewContainer"] {
            background: var(--minerva-bg) !important;
            color: var(--minerva-text) !important;
        }

        [data-testid="stHeader"] {
            background: transparent !important;
        }

        .block-container {
            max-width: 860px !important;
            padding-top: 1.1rem !important;
            padding-bottom: 6rem !important;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background: var(--minerva-white) !important;
            border-right: 1px solid var(--minerva-border);
        }

        [data-testid="stSidebar"] * {
            color: var(--minerva-text) !important;
        }

        /* Bug real: a regra acima ("*" dentro da sidebar) atinge diretamente o
           texto interno do botão "＋ Nova conversa" (que é type="primary", fundo
           azul sólido) e o força para --minerva-text (quase preto) — texto escuro
           em cima de fundo azul escuro, quase ilegível. Precisa de um seletor mais
           específico, incluindo os descendentes do botão, para vencer o "*". */
        [data-testid="stSidebar"] div.stButton > button[kind="primary"],
        [data-testid="stSidebar"] div.stButton > button[kind="primary"] *,
        [data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"],
        [data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"] * {
            color: var(--minerva-white) !important;
        }

        [data-testid="stSidebar"] .stCaptionContainer {
            color: var(--minerva-muted) !important;
        }

        .minerva-v2-sidebar-brand strong {
            font-size: 1.05rem;
        }

        .minerva-v2-sidebar-brand span {
            display: block;
            color: var(--minerva-muted);
            font-size: 0.85rem;
        }

        .minerva-v2-history-title,
        .minerva-v2-section-title,
        .minerva-v2-suggestions-label {
            font-weight: 700;
            color: var(--minerva-text);
            margin: 10px 0 6px 0;
            font-size: 0.92rem;
        }

        .minerva-v2-active {
            display: flex;
            flex-direction: column;
            gap: 2px;
            padding: 10px 14px;
            border-radius: 12px;
            background: var(--minerva-blue-soft);
            margin: 6px 0 14px 0;
        }

        .minerva-v2-active strong {
            color: var(--minerva-blue);
        }

        .minerva-v2-active span {
            color: var(--minerva-muted);
            font-size: 0.88rem;
        }

        /* Boas-vindas (tela sem mensagens) */
        .minerva-v2-intro {
            border: 1px solid var(--minerva-border);
            border-radius: 18px;
            background: var(--minerva-white);
            padding: 20px 22px;
            margin: 0 0 18px 0;
        }

        .minerva-v2-intro h2 {
            margin: 0 0 6px 0;
            font-size: 1.3rem;
            color: var(--minerva-text);
        }

        .minerva-v2-intro p {
            margin: 0;
            color: var(--minerva-muted);
            line-height: 1.5;
        }

        /* Caixa de pergunta (st.chat_input): o Streamlit pinta o wrapper
           interno com branco fixo (não usa as variáveis daqui), o que
           destoava — sobretudo no escuro, virava uma caixa branca no meio
           de uma tela escura. Mira no wrapper visível (2 níveis abaixo de
           stChatInput; sem data-testid próprio, então usa o primeiro/
           segundo filho) e aplica o tom azulado suave já usado nas bolhas
           do usuário (--minerva-blue-soft), com borda em --minerva-blue. */
        [data-testid="stChatInput"] > div {
            background: var(--minerva-blue-soft) !important;
            border: 1.5px solid var(--minerva-blue) !important;
            border-radius: 14px !important;
        }

        [data-testid="stChatInput"] textarea {
            background: transparent !important;
            color: var(--minerva-text) !important;
        }

        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--minerva-muted);
            opacity: 1;
        }

        [data-testid="stChatInput"] button {
            color: var(--minerva-blue) !important;
        }

        /* Botões */
        div.stButton > button {
            border-radius: 12px !important;
            border: 1px solid var(--minerva-border) !important;
            background: var(--minerva-white) !important;
            color: var(--minerva-text) !important;
            font-weight: 500 !important;
            box-shadow: none !important;
            transition: 0.15s ease-in-out !important;
        }

        div.stButton > button:hover {
            border-color: var(--minerva-blue) !important;
            color: var(--minerva-blue) !important;
            background: var(--minerva-blue-soft) !important;
            transform: none !important;
        }

        /* Botão "primary" (categoria ativa, Nova conversa etc.): a regra genérica
           acima forçava fundo/borda brancos em TODO botão com !important, então
           type="primary" nunca aparecia visualmente diferente de "secondary" — a
           categoria selecionada em render_cards_categorias() ficava sem nenhum
           destaque no grid de botões. Seletores redundantes porque o atributo
           "kind" e o data-testid mudaram entre versões do Streamlit. */
        div.stButton > button[kind="primary"],
        div.stButton > button[data-testid="stBaseButton-primary"],
        div.stButton > button[data-testid="baseButton-primary"] {
            border-color: var(--minerva-blue) !important;
            background: var(--minerva-blue) !important;
            color: var(--minerva-white) !important;
        }

        div.stButton > button[kind="primary"]:hover,
        div.stButton > button[data-testid="stBaseButton-primary"]:hover,
        div.stButton > button[data-testid="baseButton-primary"]:hover {
            background: var(--minerva-blue) !important;
            color: var(--minerva-white) !important;
            opacity: 0.92;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--minerva-border) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
            background: var(--minerva-white) !important;
        }

        .stDownloadButton button {
            border-radius: 12px !important;
        }

        /* Botão "⋯" (menu de renomear/excluir conversa): ícone puro, sem a
           borda/fundo padrão de botão — key="conversa_v2_menu_N" no
           st.popover() gera a classe "st-key-conversa_v2_menu_N", única
           forma estável de mirar só nesse botão (não existe seletor CSS
           por conteúdo de texto). */
        [class*="st-key-conversa_v2_menu_"] button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0.25rem 0.5rem !important;
        }

        [class*="st-key-conversa_v2_menu_"] button:hover {
            background: var(--minerva-blue-soft) !important;
        }

        /* Bolhas do chat: diferencia usuário (destacado) de assistente (neutro) */
        div[data-testid="stChatMessage"] {
            border-radius: 16px !important;
            padding: 10px 16px !important;
            margin-bottom: 10px !important;
        }

        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            background: var(--minerva-blue-soft) !important;
        }

        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
            background: var(--minerva-white) !important;
            border: 1px solid var(--minerva-border);
        }

        [data-testid="stChatInput"] {
            max-width: 860px;
            margin: auto;
        }

        hr {
            margin: 0.9rem 0 !important;
        }

        /* Imagens nunca devem estourar a coluna/container em que estão
           (o logo do cabeçalho tem width fixo em pixels — sem isso, uma
           coluna mais estreita que o valor fixo faz a imagem vazar). */
        [data-testid="stImage"] img {
            max-width: 100%;
            height: auto;
        }

        /* ------------------------------------------------------------
           RESPONSIVO — MOBILE (celular e tablets estreitos)
           ------------------------------------------------------------ */
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.85rem !important;
                padding-right: 0.85rem !important;
                padding-top: 0.85rem !important;
            }

            /* Logo do cabeçalho: cap menor pra não competir por espaço
               com o título "Minerva AI" numa tela estreita. */
            [data-testid="stImage"] img {
                max-width: 40px !important;
            }

            h2 {
                font-size: 1.3rem !important;
            }

            .minerva-v2-intro {
                padding: 16px 16px !important;
            }

            .minerva-v2-intro h2 {
                font-size: 1.15rem;
            }

            .minerva-v2-intro p {
                font-size: 0.9rem;
            }

            /* Grades de botões (categorias, perguntas sugeridas) quebram
               em 2 colunas em vez de espremer 3-4 lado a lado. Linhas que
               já tinham só 2 colunas mantêm o mesmo visual de antes. */
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                row-gap: 0.6rem !important;
            }

            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 45% !important;
                min-width: 45% !important;
                width: 45% !important;
            }

            /* Alvo de toque confortável (mínimo recomendado ~44px). */
            div.stButton > button {
                min-height: 44px !important;
                font-size: 0.85rem !important;
                padding: 0.5rem 0.6rem !important;
                white-space: normal !important;
            }

            [data-testid="stChatInput"] {
                max-width: 100% !important;
            }

            div[data-testid="stChatMessage"] {
                padding: 8px 12px !important;
                font-size: 0.94rem;
            }
        }

        /* Celulares bem estreitos: 1 botão por linha nas grades. */
        @media (max-width: 420px) {
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important;
                min-width: 100% !important;
                width: 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalizar_historico_session_state():
    """
    Corrige st.session_state.messages em memória.

    Resolve históricos antigos contendo:
    - strings
    - dicts
    - listas
    - tuplas
    """

    # Bug real (achado via streamlit.testing.v1.AppTest): esta função usava
    # st.session_state.get("messages", []) e gravava o resultado de volta
    # incondicionalmente. Numa sessão nova, "messages" ainda não existe, o
    # get() cai no default [] e o write-back CRIA a chave como lista vazia -
    # a checagem mais abaixo ("if 'messages' not in st.session_state") deixa
    # de detectar sessão nova, e carregar_historico_sessao() (restaurar do
    # banco) nunca é chamada, mesmo com o histórico salvo lá. Só normaliza
    # (e só grava de volta) quando "messages" já existe de fato.
    if "messages" not in st.session_state:
        return []

    try:

        atuais = st.session_state.get(
            "messages",
            []
        )

        normalizadas = normalizar_lista_mensagens(
            atuais
        )

        st.session_state["messages"] = (
            normalizadas
        )

        return normalizadas

    except Exception:

        return []


# Estes componentes substituem listas longas e abas por uma navegação simples:
# 1. Cards de categoria.
# 2. Perguntas rápidas por categoria.
# 3. Histórico clicável.
# 4. Exportação apenas quando houver conversa.
CATEGORIAS_MINERVA: dict[str, dict[str, list[str] | str]] = {
    "Calendário": {
        "icone": "📅",
        "descricao": "Datas, prazos, matrícula e período letivo.",
        "perguntas": [
            "Me mostre o calendário acadêmico de 2026",
            "Quais são os principais prazos do calendário acadêmico?",
            "Quando começa e termina o período letivo?",
            "Quais datas de matrícula constam no calendário?",
        ],
    },
    "Estágio": {
        "icone": "💼",
        "descricao": "Regras, documentos, matrícula e carga horária.",
        "perguntas": [
            "Quais são as regras de estágio?",
            "Como faço a matrícula de estágio?",
            "Quais documentos são necessários para estágio?",
            "Existe carga horária mínima para estágio?",
        ],
    },
    "TCC": {
        "icone": "🎓",
        "descricao": "Regulamento, banca, matrícula e defesa.",
        "perguntas": [
            "Quero saber o regulamento do TCC",
            "Como faço a matrícula do TCC?",
            "Quais regras existem para banca de TCC?",
            "Quais documentos preciso para defender o TCC?",
        ],
    },
    "Cardápio RU": {
        "icone": "🍽️",
        "descricao": "Consulta ao cardápio publicado pela PROAES.",
        "perguntas": [
            "Qual é o cardápio do RU?",
            "Qual é o cardápio de hoje?",
            "O que tem no almoço do RU?",
            "O que tem no jantar do RU?",
        ],
    },
    "Graduação": {
        "icone": "📘",
        "descricao": "Trancamento, disciplina, segunda chamada e aproveitamento.",
        "perguntas": [
            "O que diz o regulamento de graduação?",
            "Como funciona trancamento de disciplina?",
            "Como funciona segunda chamada?",
            "Como funciona aproveitamento de disciplina?",
        ],
    },
    "Normas FCT/UFPA": {
        "icone": "🏛️",
        "descricao": "Regimento da FCT e normas institucionais.",
        "perguntas": [
            "Me mostre o regimento da FCT",
            "Me mostre o regimento geral da UFPA",
            "Quais normas gerais se aplicam aos discentes?",
            "Onde encontro as regras institucionais da faculdade?",
        ],
    },
    "Guias e Manuais": {
        "icone": "📚",
        "descricao": "Tutoriais e formulários oficiais da PROEG (docentes).",
        "perguntas": [
            "Quais guias e manuais a PROEG disponibiliza?",
            "Onde encontro o tutorial do LabINFRA?",
            "Onde encontro o formulário do Avalia Docente?",
            "Onde encontro o tutorial do portal do docente no SIGAA?",
        ],
    },
}


def enviar_pergunta_minerva(pergunta: str) -> None:
    """Envia uma pergunta pronta para o chat."""
    if pergunta:
        st.session_state.messages.append({"role": "user", "content": pergunta})
        st.rerun()


def obter_perguntas_usuario():
    """
    Recupera perguntas sem assumir formato dict.
    """

    mensagens = normalizar_historico_session_state()

    return [
        mensagem_content(msg).strip()

        for msg in mensagens

        if (
            mensagem_role(msg) == "user"
            and mensagem_content(msg).strip()
        )
    ]


def gerar_txt_historico():
    """
    Exporta histórico de forma compatível
    com mensagens antigas e novas.
    """

    mensagens = normalizar_historico_session_state()

    blocos = []

    for msg in mensagens:

        role = mensagem_role(
            msg
        )

        conteudo = mensagem_content(
            msg
        ).strip()

        if not conteudo:
            continue


        if role == "user":

            rotulo = "USUÁRIO"

        elif role == "system":

            rotulo = "SISTEMA"

        else:

            rotulo = "MINERVA"


        blocos.append(
            f"{rotulo}:\n{conteudo}"
        )


    if not blocos:
        return "Histórico vazio."


    return (
        "\n\n".join(blocos)
        + "\n"
    )


def iniciar_nova_conversa() -> None:
    """Troca pra uma conversa nova e vazia.

    Reaproveitada pelo botão "＋ Nova conversa" (main.py) e por
    render_lista_conversas() quando a conversa excluída é a ativa. Não
    chama st.rerun() — fica a cargo de quem chama, depois de qualquer outra
    ação (ex. excluir_conversa) já ter sido feita.
    """
    st.session_state.conversa_id = str(uuid.uuid4())
    st.query_params["cid"] = st.session_state.conversa_id
    st.session_state.messages = []
    st.session_state.categoria_minerva_ativa = "Calendário"


@st.dialog("Excluir conversa")
def _dialog_excluir_conversa(conversa_id: str, titulo_atual: str, era_ativa: bool) -> None:
    st.write(f"Isso excluirá **{titulo_atual}**.")
    st.caption("Essa ação não pode ser desfeita.")

    col_cancelar, col_confirmar = st.columns(2)

    with col_cancelar:
        if st.button("Cancelar", key="dialog_excluir_cancelar", use_container_width=True):
            st.rerun()

    with col_confirmar:
        if st.button(
            "Excluir",
            key="dialog_excluir_confirmar",
            use_container_width=True,
            type="primary",
        ):
            excluir_conversa(conversa_id)

            if era_ativa:
                iniciar_nova_conversa()

            st.rerun()


def render_lista_conversas(conversas) -> None:
    """Mostra as conversas do dispositivo, uma por linha, estilo ChatGPT:
    título clicável (troca de conversa) + "⋯" no canto que abre um menu
    com "Renomear" (edição inline, substitui o título por um campo de
    texto na própria linha) e "Excluir" (abre modal de confirmação).

    "conversas" é o retorno de listar_conversas_dispositivo() (db.py):
    lista de (conversa_id, titulo, ultima_atividade), mais recente
    primeiro.
    """
    for idx, (conversa_id, titulo, _ultima_atividade) in enumerate(conversas):
        titulo = (titulo or "Conversa").strip()
        ativo = st.session_state.get("conversa_id") == conversa_id
        editando = st.session_state.get("editando_conversa_id") == conversa_id

        if editando:
            col_input, col_confirmar, col_cancelar = st.columns([6, 1, 1], gap="small")

            with col_input:
                novo_titulo = st.text_input(
                    "Renomear conversa",
                    value=titulo,
                    key=f"conversa_v2_rename_input_{idx}",
                    label_visibility="collapsed",
                )

            with col_confirmar:
                if st.button(
                    "✓", key=f"conversa_v2_rename_confirmar_{idx}", use_container_width=True
                ):
                    renomear_conversa(conversa_id, novo_titulo.strip() or titulo)
                    st.session_state.editando_conversa_id = None
                    st.rerun()

            with col_cancelar:
                if st.button(
                    "✕", key=f"conversa_v2_rename_cancelar_{idx}", use_container_width=True
                ):
                    st.session_state.editando_conversa_id = None
                    st.rerun()

            continue

        label = titulo
        if len(label) > 48:
            label = label[:45] + "..."

        col_titulo, col_menu = st.columns([8, 1], gap="small", vertical_alignment="center")

        with col_titulo:
            if st.button(
                label,
                key=f"conversa_v2_{idx}",
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state.conversa_id = conversa_id
                st.query_params["cid"] = conversa_id

                if "messages" in st.session_state:
                    del st.session_state["messages"]

                st.rerun()

        with col_menu, st.container(horizontal_alignment="center"):
            with st.popover("⋯", key=f"conversa_v2_menu_{idx}"):
                if st.button(
                    "✏️ Renomear", key=f"conversa_v2_edit_{idx}", use_container_width=True
                ):
                    st.session_state.editando_conversa_id = conversa_id
                    st.rerun()

                if st.button(
                    "🗑️ Excluir", key=f"conversa_v2_delete_{idx}", use_container_width=True
                ):
                    _dialog_excluir_conversa(conversa_id, titulo, ativo)


def render_cards_categorias(prefixo: str = "home") -> None:
    """Renderiza categorias compactas e perguntas sugeridas.

    Melhorias:
    - elimina duplicação visual;
    - destaca categoria selecionada;
    - usa keys exclusivas;
    - reduz altura da página.
    """
    # Bug real (achado via streamlit.testing.v1.AppTest, clique em categoria):
    # este contador era um global de módulo. Enquanto viveu em main.py (o
    # script de entrada, reexecutado do zero pelo Streamlit a cada rerun),
    # resetava para 0 a cada execução e a key do botão ficava estável entre
    # o clique e o rerun que o clique dispara. Ao mover para ui.py (módulo
    # importado normalmente, cacheado em sys.modules), o contador passou a
    # persistir e incrementar a cada rerun — a key mudava entre o clique e
    # o rerun seguinte, e o clique nunca era reconhecido. render_cards_
    # categorias só é chamada uma vez por execução (branch "home_v2" OU
    # "chat_v2" em main.py, nunca as duas), então "prefixo" já é suficiente
    # para unicidade — o contador nunca foi necessário.
    if "categoria_minerva_ativa" not in st.session_state:
        st.session_state.categoria_minerva_ativa = "Calendário"

    categorias = list(CATEGORIAS_MINERVA.keys())

    st.markdown(
        '<div class="minerva-v2-section-title">'
        'Acessos rápidos'
        '</div>',
        unsafe_allow_html=True,
    )

    # Largura fixa de coluna por linha: antes, a primeira linha (4 categorias)
    # usava st.columns(4) e a segunda (3 categorias) usava st.columns(3) — como
    # cada chamada divide o espaço disponível igualmente, os botões da segunda
    # linha ficavam visivelmente mais largos que os da primeira. Usar sempre o
    # mesmo número de colunas (colunas extras na última linha ficam vazias)
    # mantém a largura dos botões consistente entre as linhas.
    COLUNAS_POR_LINHA = 4

    for inicio_linha in range(0, len(categorias), COLUNAS_POR_LINHA):
        linha = categorias[inicio_linha : inicio_linha + COLUNAS_POR_LINHA]
        cols = st.columns(COLUNAS_POR_LINHA)

        for idx, col in enumerate(cols):
            if idx >= len(linha):
                continue

            categoria = linha[idx]
            ativo = (
                st.session_state.categoria_minerva_ativa
                == categoria
            )

            with col:
                if st.button(
                    categoria,
                    key=f"{prefixo}_cat_{inicio_linha}_{idx}",
                    use_container_width=True,
                    type="primary" if ativo else "secondary",
                ):
                    st.session_state.categoria_minerva_ativa = categoria
                    st.rerun()

    categoria_ativa = (
        st.session_state.categoria_minerva_ativa
    )

    dados = CATEGORIAS_MINERVA[categoria_ativa]
    descricao = dados.get("descricao", "")

    st.markdown(
        f"""
        <div class="minerva-v2-active">
            <strong>{categoria_ativa}</strong>
            <span>{descricao}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="minerva-v2-suggestions-label">'
        'Perguntas sugeridas'
        '</div>',
        unsafe_allow_html=True,
    )

    perguntas = dados.get("perguntas", [])
    cols = st.columns(2)

    for idx, pergunta in enumerate(perguntas):

        with cols[idx % 2]:

            if st.button(
                pergunta,
                key=f"{prefixo}_q_{idx}",
                use_container_width=True,
            ):
                enviar_pergunta_minerva(pergunta)


def render_downloads(msg: dict[str, Any], idx: int) -> None:
    """Exibe botões de download do PDF e do DOCX."""
    nome_original = msg["download_file"]
    pede_extensao = msg.get("exibir_extensao", False)

    if pede_extensao:
        caption_arquivo = f"Arquivo oficial: **{nome_original}**"
        label_pdf = "Baixar PDF"
        label_docx = "Baixar Word"
    else:
        nome_formatado = Path(nome_original).stem.replace("_", " ")
        caption_arquivo = f"Documento oficial: **{nome_formatado}**"
        label_pdf = "Baixar PDF"
        label_docx = "Baixar Word"

    st.markdown("---")
    st.caption(caption_arquivo)

    col1, col2 = st.columns(2)

    if msg.get("pdf_bytes"):
        col1.download_button(
            label=label_pdf,
            data=msg["pdf_bytes"],
            file_name=nome_original,
            mime="application/pdf",
            key=f"pdf_btn_{idx}",
        )
    else:
        col1.info("PDF original indisponível.")

    if msg.get("docx_bytes"):
        col2.download_button(
            label=label_docx,
            data=msg["docx_bytes"],
            file_name=nome_original.replace(".pdf", ".docx").replace(".PDF", ".docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"docx_btn_{idx}",
        )


def render_chat_history() -> None:
    """Renderiza o histórico completo da conversa."""
    for idx, msg in enumerate(st.session_state.messages):
        avatar = "🏫" if mensagem_role(msg) == "assistant" else "👤"

        with st.chat_message(mensagem_role(msg), avatar=avatar):
            st.markdown(mensagem_content(msg))

            if mensagem_role(msg) == "assistant" and "download_file" in msg:
                render_downloads(msg, idx)
