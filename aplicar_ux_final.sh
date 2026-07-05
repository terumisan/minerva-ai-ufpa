set -euo pipefail

APP_DIR="$HOME/ufpa_rag/app"
PROJECT_DIR="$HOME/ufpa_rag"
MAIN_FILE="$APP_DIR/main.py"

echo "Aplicando UX final da Minerva AI..."

if [[ ! -d "$APP_DIR" ]]; then
  echo "ERRO: diretório não encontrado: $APP_DIR"
  exit 1
fi

if [[ ! -f "$MAIN_FILE" ]]; then
  echo "ERRO: main.py não encontrado em: $MAIN_FILE"
  exit 1
fi

BACKUP_FILE="$APP_DIR/main.py.bkp_ux_final_$(date +%Y%m%d_%H%M%S)"
cp "$MAIN_FILE" "$BACKUP_FILE"
echo "Backup criado: $BACKUP_FILE"

cd "$APP_DIR"

python3 - <<'PY'
from pathlib import Path
import re

p = Path("main.py")
code = p.read_text(encoding="utf-8")


# =============================================================================
# 1. Garantir URL da logo
# =============================================================================
if "UFPA_LOGO_URL" not in code:
    if 'CARDAPIO_URL = get_config("CARDAPIO_URL", "https://proaes.ufpa.br/cardapio")' in code:
        code = code.replace(
            'CARDAPIO_URL = get_config("CARDAPIO_URL", "https://proaes.ufpa.br/cardapio")',
            'CARDAPIO_URL = get_config("CARDAPIO_URL", "https://proaes.ufpa.br/cardapio")\n\n'
            'UFPA_LOGO_URL = get_config(\n'
            '    "UFPA_LOGO_URL",\n'
            '    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s",\n'
            ')'
        )
    elif 'DOCUMENTOS_DIR = Path(str(get_config("DOCUMENTOS_DIR", "documentos")))' in code:
        code = code.replace(
            'DOCUMENTOS_DIR = Path(str(get_config("DOCUMENTOS_DIR", "documentos")))',
            'DOCUMENTOS_DIR = Path(str(get_config("DOCUMENTOS_DIR", "documentos")))\n\n'
            'UFPA_LOGO_URL = get_config(\n'
            '    "UFPA_LOGO_URL",\n'
            '    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s",\n'
            ')'
        )


# =============================================================================
# 2. CSS final: tema claro, logo integrada, cards limpos
# =============================================================================
ux_css = r'''

# =============================================================================
# UX FINAL - LAYOUT INSTITUCIONAL CLARO
# =============================================================================
# Objetivo:
# - Melhorar contraste.
# - Reduzir poluição visual.
# - Colocar a conversa como foco.
# - Exibir categorias principais em cards.
# - Manter histórico recolhido e clicável.
st.markdown(
    """
    <style>
    :root {
        --ufpa-blue: #1E40AF;
        --ufpa-blue-soft: #EFF6FF;
        --ufpa-border: #E5E7EB;
        --ufpa-text: #0F172A;
        --ufpa-muted: #64748B;
        --ufpa-bg: #F8FAFC;
        --ufpa-white: #FFFFFF;
    }

    html,
    body,
    .stApp,
    [data-testid="stAppViewContainer"] {
        background: var(--ufpa-bg) !important;
        color: var(--ufpa-text) !important;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }

    .block-container {
        max-width: 920px !important;
        padding-top: 1.4rem !important;
        padding-bottom: 2.5rem !important;
    }

    .minerva-topbar {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 8px 0 16px 0;
        border-bottom: 1px solid var(--ufpa-border);
        margin-bottom: 20px;
    }

    .minerva-logo {
        width: 58px;
        min-width: 58px;
        height: 58px;
        object-fit: contain;
        border-radius: 12px;
        background: #FFFFFF;
        border: 1px solid var(--ufpa-border);
        padding: 4px;
    }

    .minerva-title-wrap h1 {
        color: var(--ufpa-text) !important;
        font-size: 1.7rem !important;
        line-height: 1.15 !important;
        margin: 0 !important;
        font-weight: 800 !important;
        background: none !important;
        -webkit-text-fill-color: unset !important;
    }

    .minerva-title-wrap p {
        color: var(--ufpa-muted) !important;
        font-size: 0.94rem !important;
        margin: 4px 0 0 0 !important;
    }

    .chat-header,
    .logo-container {
        display: none !important;
    }

    .minerva-welcome {
        border: 1px solid var(--ufpa-border);
        border-radius: 18px;
        background: var(--ufpa-white);
        padding: 18px 20px;
        margin: 0 0 18px 0;
    }

    .minerva-welcome h3 {
        margin: 0 0 6px 0;
        color: var(--ufpa-text);
        font-size: 1.08rem;
        font-weight: 750;
    }

    .minerva-welcome p {
        margin: 0;
        color: var(--ufpa-muted);
        font-size: 0.94rem;
        line-height: 1.5;
    }

    .minerva-card-title {
        color: var(--ufpa-text);
        font-weight: 750;
        font-size: 0.98rem;
        margin-bottom: 4px;
    }

    .minerva-small {
        color: var(--ufpa-muted);
        font-size: 0.86rem;
    }

    .minerva-side-card {
        border: 1px solid var(--ufpa-border);
        border-radius: 16px;
        background: var(--ufpa-white);
        padding: 14px 16px;
        margin: 10px 0 14px 0;
    }

    .history-item {
        border-left: 2px solid var(--ufpa-border);
        padding-left: 10px;
        margin: 6px 0;
        color: var(--ufpa-muted);
        font-size: 0.88rem;
    }

    [data-testid="stSidebar"] {
        background: var(--ufpa-white) !important;
        border-right: 1px solid var(--ufpa-border);
    }

    [data-testid="stSidebar"] * {
        color: var(--ufpa-text) !important;
    }

    [data-testid="stSidebar"] .stCaptionContainer,
    [data-testid="stSidebar"] .minerva-small {
        color: var(--ufpa-muted) !important;
    }

    div.stButton > button {
        border-radius: 13px !important;
        border: 1px solid var(--ufpa-border) !important;
        background: var(--ufpa-white) !important;
        color: var(--ufpa-text) !important;
        font-weight: 550 !important;
        min-height: 42px !important;
        box-shadow: none !important;
        transition: 0.14s ease-in-out !important;
    }

    div.stButton > button:hover {
        border-color: var(--ufpa-blue) !important;
        color: var(--ufpa-blue) !important;
        background: var(--ufpa-blue-soft) !important;
        transform: none !important;
    }

    div[data-testid="stExpander"] {
        border: 1px solid var(--ufpa-border) !important;
        border-radius: 14px !important;
        background: var(--ufpa-white) !important;
        box-shadow: none !important;
    }

    div[data-testid="stChatMessage"] {
        background: transparent !important;
    }

    [data-testid="stChatInput"] {
        max-width: 820px;
        margin: auto;
    }

    .stDownloadButton button {
        border-radius: 13px !important;
    }

    hr {
        margin: 0.9rem 0 !important;
    }

    @media (max-width: 768px) {
        .minerva-topbar {
            align-items: flex-start;
        }

        .minerva-logo {
            width: 48px;
            min-width: 48px;
            height: 48px;
        }

        .minerva-title-wrap h1 {
            font-size: 1.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
'''

if "UX FINAL - LAYOUT INSTITUCIONAL CLARO" not in code:
    marker = "# =============================================================================\n# RECURSOS EM CACHE\n# ============================================================================="
    if marker in code:
        code = code.replace(marker, ux_css + "\n\n" + marker)
    else:
        code = code.replace("st.set_page_config(", ux_css + "\n\nst.set_page_config(", 1)


# =============================================================================
# 3. Componentes finais de UX: categorias, perguntas e histórico clicável
# =============================================================================
ux_components = r'''

# =============================================================================
# COMPONENTES FINAIS DE UX
# =============================================================================
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
}


def enviar_pergunta_minerva(pergunta: str) -> None:
    """Envia uma pergunta pronta para o chat."""
    if pergunta:
        st.session_state.messages.append({"role": "user", "content": pergunta})
        st.rerun()


def obter_perguntas_usuario() -> list[str]:
    """Retorna perguntas feitas pelo usuário na sessão atual."""
    return [
        msg.get("content", "")
        for msg in st.session_state.get("messages", [])
        if msg.get("role") == "user"
    ]


def gerar_txt_historico() -> bytes:
    """Exporta histórico da sessão em TXT."""
    linhas = ["Histórico da sessão - Minerva AI", ""]

    for msg in st.session_state.get("messages", []):
        papel = "Minerva" if msg.get("role") == "assistant" else "Usuário"
        conteudo = msg.get("content", "").strip()
        linhas.append(f"[{papel}] {conteudo}")
        linhas.append("")

    return "\n".join(linhas).encode("utf-8")


def render_historico_clicavel() -> None:
    """Mostra histórico recente como botões clicáveis para repetir consulta."""
    perguntas = obter_perguntas_usuario()

    if not perguntas:
        st.caption("Sem perguntas nesta sessão.")
        return

    for idx, pergunta in enumerate(perguntas[-6:], start=1):
        label = pergunta if len(pergunta) <= 70 else pergunta[:67] + "..."

        if st.button(label, key=f"hist_click_{idx}_{abs(hash(pergunta))}", use_container_width=True):
            enviar_pergunta_minerva(pergunta)


def render_cards_categorias(prefixo: str = "home") -> None:
    """Renderiza cards de categoria e perguntas rápidas."""
    if "categoria_minerva_ativa" not in st.session_state:
        st.session_state.categoria_minerva_ativa = "Calendário"

    categorias = list(CATEGORIAS_MINERVA.keys())

    st.markdown("#### Escolha uma categoria")

    linhas = [categorias[:4], categorias[4:]]

    for linha_idx, linha in enumerate(linhas):
        cols = st.columns(len(linha))

        for col, categoria in zip(cols, linha):
            dados = CATEGORIAS_MINERVA[categoria]
            label = f"{dados['icone']} {categoria}"

            with col:
                if st.button(label, key=f"{prefixo}_cat_{linha_idx}_{categoria}", use_container_width=True):
                    st.session_state.categoria_minerva_ativa = categoria
                    st.rerun()

    categoria_ativa = st.session_state.get("categoria_minerva_ativa", "Calendário")
    dados_ativos = CATEGORIAS_MINERVA[categoria_ativa]

    st.markdown(
        f"""
        <div class="minerva-welcome">
            <h3>{dados_ativos['icone']} {categoria_ativa}</h3>
            <p>{dados_ativos['descricao']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    perguntas = dados_ativos["perguntas"]
    cols = st.columns(2)

    for idx, pergunta in enumerate(perguntas):
        with cols[idx % 2]:
            if st.button(pergunta, key=f"{prefixo}_pergunta_{categoria_ativa}_{idx}", use_container_width=True):
                enviar_pergunta_minerva(pergunta)
'''

if "COMPONENTES FINAIS DE UX" not in code:
    marker = "# =============================================================================\n# MODELO LOCAL / FALLBACK\n# ============================================================================="
    if marker in code:
        code = code.replace(marker, ux_components + "\n\n" + marker)
    else:
        marker = "# =============================================================================\n# ESTADO DE SESSÃO\n# ============================================================================="
        code = code.replace(marker, ux_components + "\n\n" + marker)


# =============================================================================
# 4. Inicial sem balão redundante
# =============================================================================
code = re.sub(
    r'''if "messages" not in st\.session_state:\n\s+st\.session_state\.messages = \[\n\s+\{\n\s+"role": "assistant",\n\s+"content": \(\n.*?\),\n\s+\}\n\s+\]\n\n\s+registros_passados = carregar_historico_sessao\(\)''',
    '''if "messages" not in st.session_state:
    st.session_state.messages = []

    registros_passados = carregar_historico_sessao()''',
    code,
    count=1,
    flags=re.S,
)


# =============================================================================
# 5. Sidebar final: compacta, histórico clicável e exportação condicional
# =============================================================================
new_sidebar = r'''with st.sidebar:
    st.markdown("### Minerva AI")
    st.caption("FCT/UFPA")

    perguntas_usuario = obter_perguntas_usuario()
    total_perguntas = len(perguntas_usuario)

    st.markdown(
        f"""
        <div class="minerva-side-card">
            <div class="minerva-card-title">Sessão atual</div>
            <div class="minerva-small">{total_perguntas} pergunta(s) feita(s)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Nova conversa", use_container_width=True):
        if limpar_historico_banco():
            st.session_state.messages = []
            st.session_state.categoria_minerva_ativa = "Calendário"
            st.rerun()

    with st.expander("Histórico recente", expanded=False):
        render_historico_clicavel()

    with st.expander("Perguntas prontas", expanded=False):
        render_cards_categorias(prefixo="sidebar")

    if total_perguntas > 0:
        st.download_button(
            "Exportar histórico",
            data=gerar_txt_historico(),
            file_name="historico_minerva.txt",
            mime="text/plain",
            use_container_width=True,
        )


st.markdown('''

sidebar_pattern = r'with st\.sidebar:\n.*?\n\s*\nst\.markdown\('
code, n_sidebar = re.subn(sidebar_pattern, new_sidebar, code, count=1, flags=re.S)

if n_sidebar == 0:
    raise SystemExit("Não consegui localizar o bloco da sidebar.")


# =============================================================================
# 6. Cabeçalho final com logo ao lado do título
# =============================================================================
new_header = r'''st.markdown(
    f"""
    <div class="minerva-topbar">
        <img class="minerva-logo" src="{UFPA_LOGO_URL}" alt="Logo UFPA">
        <div class="minerva-title-wrap">
            <h1>Minerva AI</h1>
            <p>Orientação acadêmica baseada em documentos oficiais da FCT/UFPA</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)'''

header_patterns = [
    r'''st\.markdown\(
    f"""
    <div class="logo-container">.*?</div>
    """,
    unsafe_allow_html=True,
\)''',
    r'''st\.markdown\(
    """
    <div class="logo-container">.*?</div>
    """,
    unsafe_allow_html=True,
\)''',
    r'''st\.markdown\(
    """
    <div class="chat-header">.*?</div>
    """,
    unsafe_allow_html=True,
\)''',
]

header_ok = False

for pattern in header_patterns:
    code, n_header = re.subn(pattern, new_header, code, count=1, flags=re.S)

    if n_header:
        header_ok = True
        break

if not header_ok and "minerva-topbar" not in code:
    marker = "render_chat_history()"
    if marker in code:
        code = code.replace(marker, new_header + "\n\n" + marker, 1)
    else:
        raise SystemExit("Não consegui inserir o cabeçalho final.")


# =============================================================================
# 7. Área principal: cards de categoria, sem mensagem redundante
# =============================================================================
new_main_area = r'''# =============================================================================
# ÁREA INICIAL - CATEGORIAS E PERGUNTAS
# =============================================================================
if len(st.session_state.messages) == 0:
    st.markdown(
        """
        <div class="minerva-welcome">
            <h3>Olá, sou a Minerva.</h3>
            <p>
                Posso consultar documentos acadêmicos da FCT/UFPA e o cardápio publicado pela PROAES.
                Escolha uma categoria abaixo ou digite sua dúvida no campo principal.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_cards_categorias(prefixo="home")
else:
    with st.expander("Abrir perguntas frequentes", expanded=False):
        render_cards_categorias(prefixo="chat")


# =============================================================================
# ENTRADA DO USUÁRIO
# ============================================================================='''

area_patterns = [
    r'# =============================================================================\n# CONSULTA RÁPIDA - LAYOUT CLEAN\n# =============================================================================.*?# =============================================================================\n# ENTRADA DO USUÁRIO\n# =============================================================================',
    r'# =============================================================================\n# CENTRAL DE PERGUNTAS PRÉ-DEFINIDAS\n# =============================================================================.*?# =============================================================================\n# ENTRADA DO USUÁRIO\n# =============================================================================',
    r'# =============================================================================\n# BOTÕES DE ATALHO\n# =============================================================================.*?# =============================================================================\n# ENTRADA DO USUÁRIO\n# =============================================================================',
]

area_ok = False

for pattern in area_patterns:
    code, n_area = re.subn(pattern, new_main_area, code, count=1, flags=re.S)

    if n_area:
        area_ok = True
        break

if not area_ok:
    alvo = 'if user_query := st.chat_input('
    if alvo in code:
        code = code.replace(alvo, new_main_area + "\n" + alvo, 1)
    else:
        raise SystemExit("Não consegui localizar a entrada do usuário.")


# =============================================================================
# 8. Melhorar placeholder do chat
# =============================================================================
code = re.sub(
    r'st\.chat_input\(".*?"\)',
    'st.chat_input("Pergunte sobre calendário, estágio, TCC ou cardápio do RU...")',
    code,
    count=1,
)


# =============================================================================
# 9. Processar primeira pergunta mesmo sem mensagem inicial
# =============================================================================
code = code.replace(
    'if len(st.session_state.messages) > 1 and st.session_state.messages[-1]["role"] == "user":',
    'if len(st.session_state.messages) >= 1 and st.session_state.messages[-1]["role"] == "user":',
)


# =============================================================================
# 10. Adicionar fonte nas respostas de documentos
# =============================================================================
if 'Fonte: `{nome_arq}`' not in code:
    alvo = '        resposta = montar_resposta_documento(nome_arq, query_executar)\n        texto_formatado = formatar_documento_para_download(texto_raw, nome_arq)'
    if alvo in code:
        code = code.replace(
            alvo,
            '        resposta = montar_resposta_documento(nome_arq, query_executar)\n'
            '        if "Fonte:" not in resposta:\n'
            '            resposta = f"{resposta}\\n\\n---\\nFonte: `{nome_arq}`"\n'
            '        texto_formatado = formatar_documento_para_download(texto_raw, nome_arq)'
        )


# =============================================================================
# 11. Textos de download mais limpos
# =============================================================================
code = code.replace("📂 Arquivo oficial identificado:", "Arquivo oficial:")
code = code.replace("📂 Documento oficial disponível:", "Documento oficial:")
code = code.replace("📥 Baixar em PDF (.pdf)", "Baixar PDF")
code = code.replace("📝 Baixar em Word (.docx)", "Baixar Word")
code = code.replace("📥 Baixar Documento Oficial", "Baixar PDF")
code = code.replace("📝 Baixar Versão Editável (.docx)", "Baixar Word")
code = code.replace("Arquivo PDF original indisponível.", "PDF original indisponível.")


p.write_text(code, encoding="utf-8")
print("UX final aplicada com sucesso.")
PY


echo "Criando tema claro do Streamlit..."
mkdir -p "$APP_DIR/.streamlit"

cat > "$APP_DIR/.streamlit/config.toml" <<'TOML'
[theme]
base = "light"
primaryColor = "#1E40AF"
backgroundColor = "#F8FAFC"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#0F172A"
font = "sans serif"
TOML


echo "Garantindo secrets.toml..."
if [[ ! -f "$APP_DIR/.streamlit/secrets.toml" ]]; then
cat > "$APP_DIR/.streamlit/secrets.toml" <<'SECRETS'
DB_HOST = "ufpa_rag_db"
DB_PORT = "5432"
DB_NAME = "ufpa_rag"
DB_USER = "admin"
DB_PASSWORD = "ufpa_senha_123"
DB_POOL_MIN = "1"
DB_POOL_MAX = "10"
LLM_API_URL = "http://host.docker.internal:8001/v1/chat/completions"
DOCUMENTOS_DIR = "documentos"
CARDAPIO_URL = "https://proaes.ufpa.br/cardapio"
UFPA_LOGO_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s"
SECRETS
else
  grep -q '^CARDAPIO_URL' "$APP_DIR/.streamlit/secrets.toml" || echo 'CARDAPIO_URL = "https://proaes.ufpa.br/cardapio"' >> "$APP_DIR/.streamlit/secrets.toml"
  grep -q '^UFPA_LOGO_URL' "$APP_DIR/.streamlit/secrets.toml" || echo 'UFPA_LOGO_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s"' >> "$APP_DIR/.streamlit/secrets.toml"
fi


echo "Atualizando dependências..."
cat > "$APP_DIR/requirements.txt" <<'REQ'
streamlit
requests
psycopg2-binary
python-docx
beautifulsoup4
REQ


echo "Protegendo arquivos no Git..."
touch "$APP_DIR/.gitignore"
grep -qxF ".streamlit/secrets.toml" "$APP_DIR/.gitignore" || echo ".streamlit/secrets.toml" >> "$APP_DIR/.gitignore"
grep -qxF "__pycache__/" "$APP_DIR/.gitignore" || echo "__pycache__/" >> "$APP_DIR/.gitignore"
grep -qxF "*.pyc" "$APP_DIR/.gitignore" || echo "*.pyc" >> "$APP_DIR/.gitignore"


echo "Validando sintaxe..."
python3 -m py_compile "$MAIN_FILE"


echo "Recriando containers..."
cd "$PROJECT_DIR"
docker compose up -d --build
docker compose ps


echo ""
echo "Concluído."
echo "UX final aplicada em: $MAIN_FILE"
echo "Backup: $BACKUP_FILE"
echo ""
echo "Abra ou atualize a página com Ctrl + F5."
echo ""
echo "Logs:"
echo "cd $PROJECT_DIR && docker compose logs -f"
