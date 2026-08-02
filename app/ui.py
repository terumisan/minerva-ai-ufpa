from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

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
    from .db import renomear_conversa, excluir_conversa, registrar_feedback
except (ImportError, ValueError):
    from db import renomear_conversa, excluir_conversa, registrar_feedback
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

        /* Barra fixa do st.chat_input (rodapé): bug real visto em produção
           — o Streamlit pinta o wrapper interno dessa barra com uma cor
           quase-branca fixa própria (rgb(247,249,252), nem transparente
           nem usando tema), sem nenhum data-testid dedicado nele pra
           mirar por nome. Vira uma faixa branca destoante colada embaixo
           da tela inteira no modo escuro. O seletor por posição (filho
           direto de stBottom) é o único jeito de alcançá-lo. */
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div {
            background: var(--minerva-bg) !important;
        }

        [data-testid="stBottom"] {
            border-top: 1px solid var(--minerva-border);
        }

        .block-container {
            max-width: 860px !important;
            padding-top: 0.6rem !important;
            /* Espaço só o suficiente pra última mensagem não ficar atrás
               da barra fixa do chat_input — 6rem era generoso demais e
               empurrava a tela a precisar de scroll mesmo com pouco
               conteúdo (relatado pelo usuário). */
            padding-bottom: 2.5rem !important;
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

        /* Cartão do cabeçalho (logo+título+tema — key="header_card" no
           st.container(border=True) em main.py): o padding default do
           Streamlit pra container com borda (~1rem em todo lado) deixa o
           cabeçalho mais alto que o necessário, empurrando o resto da
           tela pra baixo e forçando scroll cedo demais (relatado pelo
           usuário). Aperta só este container específico. */
        .st-key-header_card > div {
            padding: 0.75rem 1rem !important;
        }

        /* Boas-vindas (tela sem mensagens) */
        .minerva-v2-intro {
            border: 1px solid var(--minerva-border);
            border-radius: 18px;
            background: var(--minerva-white);
            padding: 16px 22px;
            margin: 10px 0 14px 0;
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

        /* Seletor de tema (st.segmented_control, Auto/Claro/Escuro no
           cabeçalho): bug real — os 3 "pills" (role="radio" dentro do
           radiogroup) usam primaryColor/backgroundColor FIXOS do
           config.toml, os mesmos valores de tema "light" que já
           causaram os outros dois bugs de cor corrigidos antes. No
           escuro, a opção selecionada saía azul-claro sobre fundo
           azul-claro translúcido, e as não-selecionadas saíam com fundo
           quase-branco (#F7F9FC do config.toml) — exatamente o próprio
           botão que liga o modo escuro parecia continuar no claro.
           data-selected="true"/role="radio" são atributos estáveis do
           componente (ao contrário das classes st-emotion-cache-*, que
           mudam a cada build do Streamlit). */
        [role="radiogroup"] button[role="radio"] {
            background: var(--minerva-white) !important;
            color: var(--minerva-text) !important;
            border: 1px solid var(--minerva-border) !important;
        }

        [role="radiogroup"] button[role="radio"][data-selected="true"] {
            background: var(--minerva-blue) !important;
            color: var(--minerva-white) !important;
            border-color: var(--minerva-blue) !important;
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

        /* Bug real (achado com print do app em produção, modo escuro):
           o texto do conteúdo das mensagens (parágrafos, listas, negrito)
           ficava com a cor FIXA de config.toml (textColor="#0F172A",
           tema base "light" do próprio Streamlit — não muda com
           prefers-color-scheme). No modo escuro isso é texto quase-preto
           sobre balão quase-preto: ilegível. Mesmo padrão já usado na
           sidebar (seletor "* { color: ... !important }") — precisa
           mirar explicitamente nos elementos de texto do markdown pra
           vencer a cor fixa que o Streamlit aplica neles. */
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] * {
            color: var(--minerva-text) !important;
        }

        /* Links (ex.: "Fonte oficial: ...") continuam na cor de destaque —
           a regra "*" acima, sem esta exceção, apagava a diferença visual
           entre link clicável e texto normal. */
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] a {
            color: var(--minerva-blue) !important;
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


def render_acoes_resposta(msg: dict[str, Any], idx: int) -> None:
    """Botões de ação sob uma resposta do assistente: feedback (👍/👎),
    copiar e regenerar (só na última mensagem — ver comentário abaixo).
    """
    historico_id = msg.get("historico_id")
    feedback_atual = msg.get("feedback")
    eh_ultima_mensagem = idx == len(st.session_state.messages) - 1

    col_up, col_down, col_copiar, col_regenerar, _resto = st.columns(
        [1, 1, 1, 1, 8], gap="small"
    )

    with col_up:
        if st.button(
            "👍" if feedback_atual == "positivo" else "🤍",
            key=f"feedback_up_{idx}",
            help="Resposta útil",
        ) and historico_id:
            registrar_feedback(historico_id, "positivo")
            msg["feedback"] = "positivo"
            st.rerun()

    with col_down:
        if st.button(
            "👎" if feedback_atual == "negativo" else "🖤",
            key=f"feedback_down_{idx}",
            help="Resposta não ajudou",
        ) and historico_id:
            registrar_feedback(historico_id, "negativo")
            msg["feedback"] = "negativo"
            st.rerun()

    with col_copiar:
        # Streamlit não tem widget nativo de copiar pra área de
        # transferência fora de blocos de código.
        #
        # Bug real (achado testando no navegador — não só no AppTest, que
        # não pega isso): st.markdown(unsafe_allow_html=True) deixa passar
        # a TAG <button>, mas sanitiza atributos de evento inline
        # (onclick=...) por segurança — o clique não fazia nada, apesar
        # de nenhuma exceção Python ou JS aparecer em lugar nenhum.
        # components.v1.html() roda dentro de um <iframe> com JS de
        # verdade permitido — é a ferramenta certa do Streamlit pra isso,
        # não st.markdown. Efeito colateral: o iframe não herda as
        # variáveis CSS --minerva-* da página (contexto de documento
        # separado) — o botão usa cores neutras fixas + seu próprio
        # prefers-color-scheme em vez de seguir o seletor manual de tema.
        texto_b64 = base64.b64encode(mensagem_content(msg).encode("utf-8")).decode("ascii")
        components.html(
            f"""
            <style>
                body {{ margin: 0; }}
                button {{
                    border-radius: 12px; border: 1px solid #CBD5E1;
                    background: #FFFFFF; color: #0F172A;
                    padding: 0.25rem 0.6rem; cursor: pointer; font-size: 1rem;
                    height: 2.3rem; width: 100%;
                }}
                @media (prefers-color-scheme: dark) {{
                    button {{
                        border-color: #334155; background: #1E293B; color: #E2E8F0;
                    }}
                }}
            </style>
            <button id="btn-copiar" title="Copiar resposta">📋</button>
            <script>
                document.getElementById('btn-copiar').addEventListener('click', function() {{
                    const texto = decodeURIComponent(escape(atob('{texto_b64}')));
                    navigator.clipboard.writeText(texto);
                    this.innerText = '✅';
                    setTimeout(() => {{ this.innerText = '📋'; }}, 1500);
                }});
            </script>
            """,
            height=40,
        )

    with col_regenerar:
        # Só na última mensagem: regenerar uma resposta no meio da
        # conversa exigiria decidir o que fazer com as mensagens
        # seguintes (que podem referenciar o conteúdo substituído) — a
        # última é o único caso sem ambiguidade.
        if eh_ultima_mensagem and st.button(
            "🔄", key=f"regenerar_{idx}", help="Gerar outra resposta"
        ):
            # Remove a resposta atual; a pergunta correspondente (idx-1)
            # volta a ser "a última mensagem é do usuário" — o mesmo
            # gatilho que já dispara uma geração nova no fim do main.py,
            # reaproveitando o pipeline inteiro (streaming, rota,
            # latência) em vez de duplicar essa lógica aqui.
            st.session_state.messages.pop(idx)
            st.rerun()


def render_chat_history() -> None:
    """Renderiza o histórico completo da conversa."""
    for idx, msg in enumerate(st.session_state.messages):
        avatar = "🏫" if mensagem_role(msg) == "assistant" else "👤"

        with st.chat_message(mensagem_role(msg), avatar=avatar):
            st.markdown(mensagem_content(msg))

            if mensagem_role(msg) == "assistant" and "download_file" in msg:
                render_downloads(msg, idx)

            if mensagem_role(msg) == "assistant":
                render_acoes_resposta(msg, idx)
