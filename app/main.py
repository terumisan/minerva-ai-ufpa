from __future__ import annotations

import os
import re
import uuid
import logging
import unicodedata
from io import BytesIO
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
import streamlit as st
import psycopg2
from psycopg2 import pool
from docx import Document


# =============================================================================
# MINERVA AI - FCT/UFPA
# -----------------------------------------------------------------------------
# Aplicação Streamlit para orientação acadêmica baseada em documentos oficiais.
#
# Melhorias aplicadas:
# - Código mais organizado por blocos.
# - Comentários explicando os principais trechos.
# - Credenciais fora do código-fonte.
# - Histórico separado por sessão.
# - Tratamento de erro com rollback.
# - Busca por intenção.
# - Download em PDF oficial e DOCX real.
# - Prompt de segurança para evitar respostas inventadas.
# =============================================================================


# =============================================================================
# LOGGING
# =============================================================================
# O logging registra falhas técnicas no console/container sem exibir stack trace
# para o usuário final.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("minerva")


# =============================================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# =============================================================================
st.set_page_config(
    page_title="Minerva - FCT/UFPA",
    layout="centered",
    page_icon="🏫",
    initial_sidebar_state="expanded",
)


# =============================================================================
# CONFIGURAÇÕES SEGURAS
# =============================================================================
def get_config(nome: str, padrao: Any = None) -> Any:
    """Busca configuração primeiro em st.secrets, depois em variável de ambiente.

    Ordem:
    1. .streamlit/secrets.toml
    2. Variável de ambiente
    3. Valor padrão
    """
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass

    return os.getenv(nome, padrao)


DB_HOST = get_config("DB_HOST", "ufpa_rag_db")
DB_PORT = int(get_config("DB_PORT", "5432"))
DB_NAME = get_config("DB_NAME", "ufpa_rag")
DB_USER = get_config("DB_USER", "admin")
DB_PASSWORD = get_config("DB_PASSWORD", "ufpa_senha_123")

DB_POOL_MIN = int(get_config("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(get_config("DB_POOL_MAX", "10"))

LLM_API_URL = get_config(
    "LLM_API_URL",
    "http://host.docker.internal:8001/v1/chat/completions",
)

DOCUMENTOS_DIR = Path(str(get_config("DOCUMENTOS_DIR", "documentos")))

UFPA_LOGO_URL = get_config(
    "UFPA_LOGO_URL",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s",
)

CARDAPIO_URL = get_config("CARDAPIO_URL", "https://proaes.ufpa.br/cardapio")


# =============================================================================
# CSS DA INTERFACE
# =============================================================================
st.markdown(
    """
    <style>
    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding-top: 10px;
        margin-bottom: 5px;
    }

    .logo-img {
        width: 86px !important;
        height: auto !important;
        object-fit: contain;
        opacity: 0.96;
    }

    .chat-header {
        text-align: center;
        padding: 0px 0 10px 0;
    }

    .chat-header h1 {
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        background: linear-gradient(45deg, #1E40AF, #3B82F6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 5px 0;
    }

    .chat-header p {
        color: #6B7280;
        font-size: 1rem;
    }

    .stSidebar {
        background-color: #0F172A !important;
    }

    .stSidebar h3,
    .stSidebar h4,
    .stSidebar p,
    .stSidebar span {
        color: #F8FAFC !important;
    }

    div.stButton > button:first-child {
        border-radius: 20px;
        border: 1px solid #E2E8F0;
        background-color: #FFFFFF;
        color: #1E40AF;
        font-weight: 500;
        transition: all 0.3s ease;
    }

    div.stButton > button:first-child:hover {
        background-color: #1E40AF;
        color: #FFFFFF;
        border-color: #1E40AF;
        transform: translateY(-2px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)




# -----------------------------------------------------------------------------
# MELHORIAS DE LAYOUT DO FRONT-END
# -----------------------------------------------------------------------------
# Este bloco adiciona cards, área de boas-vindas, histórico visual e pequenos
# ajustes de espaçamento. Mantém o visual institucional sem alterar a lógica.
st.markdown(
    """
    <style>
    .minerva-hero {
        border: 1px solid #E5E7EB;
        border-radius: 22px;
        padding: 22px 24px;
        margin: 8px 0 20px 0;
        background: linear-gradient(135deg, #EFF6FF 0%, #FFFFFF 70%);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }

    .minerva-hero h3 {
        margin: 0 0 8px 0;
        color: #0F172A;
        font-weight: 800;
    }

    .minerva-hero p {
        margin: 0;
        color: #475569;
        line-height: 1.55;
    }

    .minerva-card {
        border: 1px solid #E5E7EB;
        border-radius: 18px;
        padding: 14px 16px;
        background: #FFFFFF;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
        margin-bottom: 10px;
    }

    .minerva-muted {
        color: #64748B;
        font-size: 0.92rem;
    }

    .history-item {
        border-left: 3px solid #3B82F6;
        padding-left: 10px;
        margin: 8px 0;
        color: #334155;
        font-size: 0.92rem;
    }

    div[data-testid="stExpander"] {
        border-radius: 16px !important;
        border-color: #E5E7EB !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 999px;
        padding: 8px 14px;
        background-color: #F8FAFC;
    }
    </style>
    """,
    unsafe_allow_html=True,
)




# =============================================================================
# LAYOUT CLEAN - MINERVA AI
# =============================================================================
# Este bloco reduz poluição visual:
# - remove excesso de sombras e bordas;
# - compacta o cabeçalho;
# - suaviza botões;
# - cria uma área inicial mais institucional;
# - deixa histórico e perguntas frequentes menos invasivos.
st.markdown(
    """
    <style>
    :root {
        --minerva-blue: #1E40AF;
        --minerva-blue-soft: #EFF6FF;
        --minerva-border: #E5E7EB;
        --minerva-text: #0F172A;
        --minerva-muted: #64748B;
        --minerva-bg: #F8FAFC;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 860px;
    }

    .logo-container {
        display: flex !important;
        justify-content: center;
        align-items: center;
        margin: 4px 0 10px 0;
    }

    .logo-img {
        width: 86px !important;
        height: auto !important;
        object-fit: contain;
        opacity: 0.96;
    }

    .chat-header {
        text-align: left !important;
        padding: 6px 0 12px 0 !important;
        border-bottom: 1px solid var(--minerva-border);
        margin-bottom: 18px;
    }

    .chat-header h1 {
        font-size: 1.75rem !important;
        margin: 0 0 4px 0 !important;
        color: var(--minerva-text) !important;
        background: none !important;
        -webkit-text-fill-color: unset !important;
        font-weight: 800 !important;
    }

    .chat-header p {
        color: var(--minerva-muted) !important;
        font-size: 0.95rem !important;
        margin: 0 !important;
    }

    .minerva-clean-hero {
        border: 1px solid var(--minerva-border);
        border-radius: 18px;
        padding: 18px 20px;
        margin: 0 0 18px 0;
        background: #FFFFFF;
    }

    .minerva-clean-hero h3 {
        margin: 0 0 6px 0;
        font-size: 1.12rem;
        color: var(--minerva-text);
        font-weight: 750;
    }

    .minerva-clean-hero p {
        margin: 0;
        color: var(--minerva-muted);
        line-height: 1.5;
        font-size: 0.94rem;
    }

    .minerva-panel {
        border: 1px solid var(--minerva-border);
        border-radius: 16px;
        background: #FFFFFF;
        padding: 14px 16px;
        margin-bottom: 14px;
    }

    .minerva-panel-title {
        font-weight: 700;
        color: var(--minerva-text);
        margin-bottom: 4px;
    }

    .minerva-small {
        color: var(--minerva-muted);
        font-size: 0.9rem;
    }

    .stSidebar {
        background: #FFFFFF !important;
        border-right: 1px solid var(--minerva-border);
    }

    .stSidebar h1,
    .stSidebar h2,
    .stSidebar h3,
    .stSidebar h4,
    .stSidebar p,
    .stSidebar span,
    .stSidebar label {
        color: var(--minerva-text) !important;
    }

    div.stButton > button {
        border-radius: 12px !important;
        border: 1px solid var(--minerva-border) !important;
        background: #FFFFFF !important;
        color: var(--minerva-text) !important;
        font-weight: 500 !important;
        box-shadow: none !important;
        transition: 0.15s ease-in-out !important;
    }

    div.stButton > button:hover {
        border-color: var(--minerva-blue) !important;
        color: var(--minerva-blue) !important;
        transform: none !important;
    }

    div[data-testid="stExpander"] {
        border: 1px solid var(--minerva-border) !important;
        border-radius: 14px !important;
        box-shadow: none !important;
        background: #FFFFFF !important;
    }

    div[data-testid="stChatMessage"] {
        border-radius: 16px;
        padding: 2px 0;
    }

    .history-item {
        border-left: 2px solid var(--minerva-border);
        padding-left: 10px;
        margin: 6px 0;
        color: var(--minerva-muted);
        font-size: 0.88rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        display: none !important;
    }

    hr {
        margin: 1rem 0 !important;
    }

    .stDownloadButton button {
        border-radius: 12px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)




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




# =============================================================================
# UX V2 - INTERFACE INSTITUCIONAL MODERNA
# =============================================================================
# Este bloco prioriza:
# - menos poluição visual;
# - melhor hierarquia;
# - campo de pergunta em destaque;
# - sidebar compacta;
# - categorias sem duplicação;
# - responsividade.



# FIX VISUAL CABECALHO NATIVO V4
st.markdown("""
<style>
/* Menos espaço no topo */
.block-container {
    padding-top: 1.1rem !important;
}

/* Título do cabeçalho */
[data-testid="stMainBlockContainer"] h2 {
    margin-top: 0 !important;
    margin-bottom: 0.1rem !important;
    color: #0F172A !important;
    font-size: 1.55rem !important;
    line-height: 1.15 !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
}

/* Subtítulo */
[data-testid="stMainBlockContainer"] [data-testid="stCaptionContainer"] {
    margin-top: 0 !important;
}

/* Divisor mais suave */
[data-testid="stMainBlockContainer"] hr {
    margin-top: 0.65rem !important;
    margin-bottom: 1.15rem !important;
    border-color: #E2E8F0 !important;
}

/* Mobile */
@media (max-width: 768px) {
    [data-testid="stMainBlockContainer"] h2 {
        font-size: 1.3rem !important;
    }
}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# RECURSOS EM CACHE
# =============================================================================
@st.cache_resource(show_spinner=False)
def get_http_session() -> requests.Session:
    """Cria sessão HTTP reutilizável para chamadas ao modelo local."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@st.cache_resource(show_spinner=False)
def get_db_pool() -> pool.SimpleConnectionPool | None:
    """Cria pool de conexões PostgreSQL.

    O pool evita abrir e fechar conexão a cada pergunta.
    """
    try:
        return psycopg2.pool.SimpleConnectionPool(
            minconn=DB_POOL_MIN,
            maxconn=DB_POOL_MAX,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
    except Exception as exc:
        logger.exception("Erro ao inicializar pool de banco: %s", exc)
        return None


http_session = get_http_session()
db_pool = get_db_pool()


# =============================================================================
# BANCO DE DADOS
# =============================================================================
def executar_query(
    sql: str,
    params: tuple[Any, ...] | None = None,
    *,
    fetch: bool = False,
    commit: bool = False,
) -> list[tuple[Any, ...]] | None:
    """Executa SQL de forma centralizada.

    Faz rollback em caso de erro e devolve a conexão para o pool.
    """
    if not db_pool:
        logger.error("Pool de banco indisponível.")
        return None

    conn = None
    resultado = None

    try:
        conn = db_pool.getconn()

        with conn.cursor() as cur:
            cur.execute(sql, params)

            if fetch:
                resultado = cur.fetchall()

            if commit:
                conn.commit()

    except Exception as exc:
        if conn:
            conn.rollback()

        logger.exception("Erro ao executar query: %s", exc)
        return None

    finally:
        if conn:
            db_pool.putconn(conn)

    return resultado


def inicializar_banco() -> None:
    """Garante a existência da tabela de histórico.

    A coluna session_id separa conversas de usuários diferentes.
    """
    executar_query(
        """
        CREATE TABLE IF NOT EXISTS historico_minerva (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pergunta TEXT,
            resposta TEXT
        );
        """,
        commit=True,
    )

    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS session_id TEXT;",
        commit=True,
    )

    executar_query(
        "UPDATE historico_minerva SET session_id = 'legacy' WHERE session_id IS NULL;",
        commit=True,
    )


def salvar_no_historico(pergunta: str, resposta: str) -> None:
    """Salva pergunta e resposta da sessão atual."""
    executar_query(
        """
        INSERT INTO historico_minerva (session_id, pergunta, resposta)
        VALUES (%s, %s, %s);
        """,
        params=(st.session_state.session_id, pergunta, resposta),
        commit=True,
    )


def limpar_historico_banco() -> bool:
    """Remove apenas o histórico da sessão atual."""
    try:
        executar_query(
            "DELETE FROM historico_minerva WHERE session_id = %s;",
            params=(st.session_state.session_id,),
            commit=True,
        )
        return True

    except Exception as exc:
        logger.exception("Erro ao limpar histórico: %s", exc)
        return False


def carregar_historico_sessao() -> list[tuple[str, str]]:
    """Carrega o histórico persistido da sessão atual."""
    registros = executar_query(
        """
        SELECT pergunta, resposta
        FROM historico_minerva
        WHERE session_id = %s
        ORDER BY id ASC;
        """,
        params=(st.session_state.session_id,),
        fetch=True,
    )

    return registros or []


# =============================================================================
# DOCUMENTOS E DOWNLOADS
# =============================================================================
def caminhos_documento(nome_arquivo: str) -> Iterable[Path]:
    """Retorna caminhos prováveis para localizar os PDFs oficiais.

    Compatível com execução local e com Docker.
    """
    yield DOCUMENTOS_DIR / nome_arquivo
    yield Path("..") / "documentos" / nome_arquivo
    yield Path("/app") / "documentos" / nome_arquivo
    yield Path("/documentos") / nome_arquivo
    yield Path(nome_arquivo)


def obter_binario_pdf(nome_arquivo: str) -> bytes | None:
    """Obtém o arquivo PDF original em bytes."""
    for caminho in caminhos_documento(nome_arquivo):
        if caminho.exists():
            try:
                return caminho.read_bytes()
            except Exception as exc:
                logger.exception("Erro ao ler PDF em %s: %s", caminho, exc)

    return None


def formatar_documento_para_download(texto_bruto: str | None, nome_arquivo: str) -> str:
    """Formata texto bruto extraído do banco para gerar DOCX editável."""
    if not texto_bruto:
        return "Conteúdo indisponível para estruturação."

    if "calendario" in nome_arquivo.lower() or "calendário" in nome_arquivo.lower():
        texto = texto_bruto

        meses = {
            r"J\s*A\s*N\s*E\s*I\s*R\s*O": "\n\n📅 [ JANEIRO ] ───────────────────\n",
            r"F\s*E\s*V\s*E\s*R\s*E\s*I\s*R\s*O": "\n\n📅 [ FEVEREIRO ] ─────────────────\n",
            r"M\s*A\s*R\s*Ç\s*O": "\n\n📅 [ MARÇO ] ────────────────────\n",
            r"A\s*B\s*R\s*I\s*L": "\n\n📅 [ ABRIL ] ────────────────────\n",
            r"M\s*A\s*I\s*O": "\n\n📅 [ MAIO ] ─────────────────────\n",
            r"J\s*U\s*N\s*H\s*O": "\n\n📅 [ JUNHO ] ────────────────────\n",
            r"J\s*U\s*L\s*H\s*O": "\n\n📅 [ JULHO ] ────────────────────\n",
            r"A\s*G\s*O\s*S\s*T\s*O": "\n\n📅 [ AGOSTO ] ───────────────────\n",
            r"S\s*E\s*T\s*E\s*M\s*B\s*R\s*O": "\n\n📅 [ SETEMBRO ] ─────────────────\n",
            r"O\s*U\s*T\s*U\s*B\s*R\s*O": "\n\n📅 [ OUTUBRO ] ──────────────────\n",
            r"N\s*O\s*V\s*E\s*M\s*B\s*R\s*O": "\n\n📅 [ NOVEMBRO ] ─────────────────\n",
            r"D\s*E\s*Z\s*E\s*M\s*B\s*R\s*O": "\n\n📅 [ DEZEMBRO ] ─────────────────\n",
        }

        for regex_mes, substituto in meses.items():
            texto = re.sub(regex_mes, substituto, texto, flags=re.IGNORECASE)

        return texto.strip()

    texto_limpo = re.sub(r"\s+", " ", texto_bruto).strip()
    return re.sub(r"\.\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ])", r".\n\n\1", texto_limpo)


def gerar_docx(texto_estruturado: str) -> bytes:
    """Gera arquivo DOCX real com python-docx."""
    doc = Document()
    doc.add_heading("DOCUMENTO OFICIAL EMITIDO PELA MINERVA AI", level=1)

    for paragrafo in texto_estruturado.split("\n"):
        paragrafo = paragrafo.strip()

        if paragrafo:
            doc.add_paragraph(paragrafo)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer.getvalue()




# =============================================================================
# CARDÁPIO PROAES / RESTAURANTE UNIVERSITÁRIO
# =============================================================================
# Este bloco permite que a Minerva consulte o cardápio publicado pela PROAES.
# Fluxo:
# 1. Detecta perguntas sobre cardápio, RU, almoço ou jantar.
# 2. Acessa https://proaes.ufpa.br/cardapio.
# 3. Extrai dia, data, almoço, jantar e itens do cardápio.
# 4. Se não houver informação extraída, responde que não há cardápio disponível.
@st.cache_data(ttl=1800, show_spinner=False)
def obter_cardapio_proaes() -> list[dict[str, Any]]:
    """Consulta e extrai o cardápio publicado no site da PROAES.

    O cache de 30 minutos evita consultar o site a cada pergunta, mas mantém
    a resposta suficientemente atualizada para uso diário.
    """
    try:
        response = http_session.get(
            CARDAPIO_URL,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MinervaAI/1.0; "
                    "+https://proaes.ufpa.br/cardapio)"
                )
            },
        )
        response.raise_for_status()

    except Exception as exc:
        logger.exception("Erro ao acessar cardápio PROAES: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    texto = soup.get_text("\n", strip=True)

    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]

    if not linhas:
        return []

    return extrair_cardapio_das_linhas(linhas)


def remover_acentos(texto: str) -> str:
    """Remove acentos para facilitar comparação de termos."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", texto)
        if unicodedata.category(char) != "Mn"
    )


def normalizar_cardapio_texto(texto: str) -> str:
    """Normaliza texto usado na detecção do cardápio."""
    texto = remover_acentos(texto.lower().strip())
    texto = re.sub(r"\s+", " ", texto)
    return texto


def eh_linha_dia(linha: str) -> bool:
    """Identifica linhas com nome de dia da semana."""
    dias = {
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo",
    }

    return normalizar_cardapio_texto(linha) in dias


def eh_linha_data(linha: str) -> bool:
    """Identifica datas no formato DD/MM/AAAA."""
    return bool(re.fullmatch(r"\d{2}/\d{2}/\d{4}", linha.strip()))


def eh_linha_refeicao(linha: str) -> bool:
    """Identifica ALMOÇO ou JANTAR."""
    return normalizar_cardapio_texto(linha) in {"almoco", "jantar"}


def extrair_cardapio_das_linhas(linhas: list[str]) -> list[dict[str, Any]]:
    """Transforma o texto da página em uma estrutura de cardápio."""
    cardapio: list[dict[str, Any]] = []
    i = 0

    while i < len(linhas):
        linha = linhas[i]

        if not eh_linha_dia(linha):
            i += 1
            continue

        dia = linha.upper()
        data = ""

        i += 1

        if i < len(linhas) and eh_linha_data(linhas[i]):
            data = linhas[i]
            i += 1

        refeicoes: list[dict[str, Any]] = []

        while i < len(linhas) and not eh_linha_dia(linhas[i]):
            linha_atual = linhas[i]

            if not eh_linha_refeicao(linha_atual):
                i += 1
                continue

            tipo_refeicao = remover_acentos(linha_atual.upper())
            tipo_refeicao = "ALMOÇO" if tipo_refeicao == "ALMOCO" else "JANTAR"

            i += 1
            secoes: dict[str, list[str]] = {}
            secao_atual = None

            while (
                i < len(linhas)
                and not eh_linha_dia(linhas[i])
                and not eh_linha_refeicao(linhas[i])
            ):
                item = linhas[i].strip()

                # Ignora fragmentos de navegação/rodapé que podem aparecer no HTML.
                item_normalizado = normalizar_cardapio_texto(item)

                if item_normalizado in {
                    "acesso rapido",
                    "fale conosco siga-nos",
                    "assistencia estudantil por campi",
                    "copyright",
                }:
                    i += 1
                    continue

                if item.endswith(":"):
                    secao_atual = item[:-1].strip()
                    secoes.setdefault(secao_atual, [])

                elif secao_atual:
                    secoes.setdefault(secao_atual, []).append(item)

                i += 1

            if secoes:
                refeicoes.append(
                    {
                        "tipo": tipo_refeicao,
                        "secoes": secoes,
                    }
                )

        if dia and data and refeicoes:
            cardapio.append(
                {
                    "dia": dia,
                    "data": data,
                    "refeicoes": refeicoes,
                }
            )

    return cardapio


def eh_pergunta_cardapio(query: str) -> bool:
    """Detecta se o usuário está perguntando sobre cardápio/RU."""
    query_lc = normalizar_cardapio_texto(query)

    termos = [
        "cardapio",
        "cardapio do ru",
        "ru",
        "restaurante universitario",
        "bandejao",
        "almoco",
        "jantar",
        "comida de hoje",
        "o que tem para comer",
        "o que vai ter no almoco",
        "o que vai ter no jantar",
    ]

    return any(termo in query_lc for termo in termos)


def filtrar_cardapio_por_pergunta(
    cardapio: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Filtra o cardápio por hoje ou por dia da semana, quando solicitado."""
    if not cardapio:
        return []

    query_lc = normalizar_cardapio_texto(query)

    if "hoje" in query_lc:
        hoje = date.today().strftime("%d/%m/%Y")
        return [item for item in cardapio if item.get("data") == hoje]

    dias_busca = {
        "segunda": "SEGUNDA",
        "terca": "TERÇA",
        "quarta": "QUARTA",
        "quinta": "QUINTA",
        "sexta": "SEXTA",
        "sabado": "SÁBADO",
        "domingo": "DOMINGO",
    }

    for termo, dia_formatado in dias_busca.items():
        if termo in query_lc:
            return [
                item
                for item in cardapio
                if normalizar_cardapio_texto(item.get("dia", "")) == termo
            ]

    return cardapio


def filtrar_refeicoes_por_pergunta(
    refeicoes: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Filtra almoço ou jantar quando o usuário especifica uma refeição."""
    query_lc = normalizar_cardapio_texto(query)

    if "almoco" in query_lc:
        return [r for r in refeicoes if normalizar_cardapio_texto(r.get("tipo", "")) == "almoco"]

    if "jantar" in query_lc:
        return [r for r in refeicoes if normalizar_cardapio_texto(r.get("tipo", "")) == "jantar"]

    return refeicoes


def formatar_cardapio_resposta(cardapio: list[dict[str, Any]], query: str) -> str:
    """Formata a resposta do cardápio para o chat."""
    if not cardapio:
        return "Não há cardápio disponível no momento no site da PROAES."

    cardapio_filtrado = filtrar_cardapio_por_pergunta(cardapio, query)

    if not cardapio_filtrado:
        return "Não há cardápio disponível no momento no site da PROAES."

    linhas = [
        "Consultei o cardápio publicado pela **PROAES/UFPA**.",
        "",
    ]

    for dia_info in cardapio_filtrado:
        linhas.append(f"### {dia_info['dia']} - {dia_info['data']}")

        refeicoes = filtrar_refeicoes_por_pergunta(dia_info.get("refeicoes", []), query)

        if not refeicoes:
            linhas.append("Não há informação da refeição solicitada para este dia.")
            linhas.append("")
            continue

        for refeicao in refeicoes:
            linhas.append(f"**{refeicao['tipo']}**")

            for secao, itens in refeicao.get("secoes", {}).items():
                if not itens:
                    continue

                linhas.append(f"- **{secao}:** {', '.join(itens)}")

            linhas.append("")

    linhas.append("---")
    linhas.append("Fonte: site da PROAES/UFPA.")

    resposta = "\n".join(linhas).strip()

    if resposta.count("###") == 0:
        return "Não há cardápio disponível no momento no site da PROAES."

    return resposta


def responder_cardapio_proaes(query: str) -> str:
    """Função principal chamada pelo fluxo do chat."""
    cardapio = obter_cardapio_proaes()
    return formatar_cardapio_resposta(cardapio, query)


# =============================================================================
# BUSCA POR INTENÇÃO
# =============================================================================
# Mapeia termos do usuário para documentos oficiais.
# Isso é mais confiável do que depender apenas do nome exato do arquivo.
INTENCOES_DOCUMENTOS: dict[str, list[str]] = {
    "CalendarioAcademico2026.pdf": [
        "calendario",
        "calendário",
        "cronograma",
        "prazos",
        "datas",
        "periodo letivo",
        "período letivo",
        "feriado",
        "matricula",
        "matrícula",
        "rematricula",
        "rematrícula",
    ],
    "Resolucao_Estagio.pdf": [
        "estagio",
        "estágio",
        "resolucao estagio",
        "resolução estágio",
        "termo de compromisso",
        "supervisor",
        "relatorio de estagio",
        "relatório de estágio",
        "carga horária estágio",
    ],
    "Matricula_Estagio.pdf": [
        "matricula estagio",
        "matrícula estágio",
        "inscrição estágio",
        "inscricao estagio",
    ],
    "Resolucao_TCC.pdf": [
        "tcc",
        "trabalho de conclusao",
        "trabalho de conclusão",
        "banca",
        "defesa",
        "orientador",
        "monografia",
    ],
    "Matricula_TCC.pdf": [
        "matricula tcc",
        "matrícula tcc",
        "inscrição tcc",
        "inscricao tcc",
    ],
    "Regimento_FCT.pdf": [
        "regimento fct",
        "normas fct",
        "faculdade de computação",
        "faculdade de computacao",
    ],
    "RegimentoGeral.pdf": [
        "regimento geral",
        "normas gerais ufpa",
    ],
    "Regulamento_Graduacao.pdf": [
        "graduacao",
        "graduação",
        "trancamento",
        "disciplina",
        "aproveitamento",
        "segunda chamada",
        "frequência",
        "frequencia",
        "conceito",
        "coeficiente",
    ],
    "Resolucao_Ativ_Complementares.pdf": [
        "atividade complementar",
        "atividades complementares",
        "horas complementares",
    ],
    "Resolucao_Intercambios.pdf": [
        "intercambio",
        "intercâmbio",
        "mobilidade academica",
        "mobilidade acadêmica",
    ],
    "Resolucao_PraticasEnsino.pdf": [
        "pratica de ensino",
        "prática de ensino",
        "praticas de ensino",
        "práticas de ensino",
    ],
}


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para busca por termos."""
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\sáéíóúâêôãõç]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto


def pontuar_documento(query_normalizada: str, termos: list[str]) -> int:
    """Calcula pontuação de compatibilidade entre pergunta e documento."""
    return sum(1 for termo in termos if termo in query_normalizada)


def buscar_contexto_e_arquivo(query: str) -> tuple[str | None, str | None]:
    """Busca documento oficial relacionado à pergunta.

    Fluxo:
    1. Identifica intenção por palavras associadas.
    2. Busca o documento no banco.
    3. Se não encontrar, tenta fallback por nome de arquivo.
    """
    query_lc = normalizar_texto(query)

    melhor_arquivo = None
    maior_pontuacao = 0

    for nome_arquivo, termos in INTENCOES_DOCUMENTOS.items():
        pontuacao = pontuar_documento(query_lc, termos)

        if pontuacao > maior_pontuacao:
            maior_pontuacao = pontuacao
            melhor_arquivo = nome_arquivo

    if melhor_arquivo:
        resultados = executar_query(
            """
            SELECT nome_arquivo, conteudo
            FROM documentos_ufpa
            WHERE nome_arquivo = %s
            LIMIT 1;
            """,
            params=(melhor_arquivo,),
            fetch=True,
        )

        if resultados:
            return resultados[0][0], resultados[0][1]

    palavras = [p for p in re.findall(r"\w+", query_lc) if len(p) > 3]

    if palavras:
        condicoes = " OR ".join(["nome_arquivo ILIKE %s" for _ in palavras])
        params = tuple(f"%{p}%" for p in palavras)

        resultados = executar_query(
            f"""
            SELECT nome_arquivo, conteudo
            FROM documentos_ufpa
            WHERE ({condicoes})
            LIMIT 1;
            """,
            params=params,
            fetch=True,
        )

        if resultados:
            return resultados[0][0], resultados[0][1]

    return None, None


def usuario_pediu_formato(query: str) -> bool:
    """Verifica se o usuário pediu PDF, Word, DOCX ou formato específico."""
    termos = ["extensão", "extensao", "pdf", "word", "doc", "docx", "formato"]
    query_lc = query.lower()

    return any(termo in query_lc for termo in termos)


def montar_resposta_documento(nome_arquivo: str, query: str) -> str:
    """Monta resposta institucional para o documento encontrado."""
    query_lc = query.lower()

    if "calendario" in query_lc or "calendário" in query_lc or "cronograma" in query_lc:
        return (
            "Localizei o **Calendário Acadêmico Oficial de 2026** na base institucional.\n\n"
            "Para preservar a precisão das datas, consulte o documento original disponível abaixo."
        )

    if "estagio" in query_lc or "estágio" in query_lc:
        return (
            "Localizei documento compatível com **Estágio** na base institucional da FCT/UFPA.\n\n"
            "Consulte o arquivo abaixo para verificar requisitos, fluxos e orientações oficiais."
        )

    if "tcc" in query_lc:
        return (
            "Localizei documento compatível com **Trabalho de Conclusão de Curso (TCC)**.\n\n"
            "Consulte o arquivo abaixo para verificar regras, prazos, banca e demais orientações oficiais."
        )

    nome_amigavel = Path(nome_arquivo).stem.replace("_", " ")

    return (
        f"Localizei um documento compatível com sua solicitação: **{nome_amigavel}**.\n\n"
        "Consulte o arquivo abaixo para confirmar as informações oficiais."
    )




# =============================================================================
# PERGUNTAS PRÉ-DEFINIDAS PARA O FRONT-END
# =============================================================================
# Esta lista organiza dúvidas comuns por categoria. Isso ajuda o discente a
# começar a conversa sem precisar saber exatamente como formular a pergunta.
PERGUNTAS_PRE_DEFINIDAS: dict[str, list[str]] = {
    "🍽️ Cardápio RU": [
        "Qual é o cardápio do RU?",
        "Qual é o cardápio de hoje?",
        "O que tem no almoço do RU?",
        "O que tem no jantar do RU?",
    ],
    "📅 Calendário": [
        "Me mostre o calendário acadêmico de 2026",
        "Quais são os principais prazos do calendário acadêmico?",
        "Quando começa e termina o período letivo?",
        "Quais datas de matrícula e rematrícula constam no calendário?",
    ],
    "💼 Estágio": [
        "Quais são as regras de estágio?",
        "Como faço a matrícula de estágio?",
        "Quais documentos são necessários para estágio?",
        "Existe carga horária mínima para estágio?",
    ],
    "🎓 TCC": [
        "Quero saber o regulamento do TCC",
        "Como faço a matrícula do TCC?",
        "Quais regras existem para banca de TCC?",
        "Quais documentos preciso para defender o TCC?",
    ],
    "📘 Graduação": [
        "O que diz o regulamento de graduação?",
        "Como funciona trancamento de disciplina?",
        "Como funciona segunda chamada?",
        "Como funciona aproveitamento de disciplina?",
    ],
    "🏛️ Normas FCT/UFPA": [
        "Me mostre o regimento da FCT",
        "Me mostre o regimento geral da UFPA",
        "Quais normas gerais se aplicam aos discentes?",
        "Onde encontro as regras institucionais da faculdade?",
    ],
    "⭐ Atividades e Mobilidade": [
        "Quais são as regras de atividades complementares?",
        "Como funcionam as horas complementares?",
        "Quais são as regras de intercâmbio?",
        "Como funciona mobilidade acadêmica?",
    ],
}


def adicionar_pergunta_rapida(pergunta: str) -> None:
    """Adiciona pergunta pré-definida ao chat e dispara o processamento."""
    st.session_state.messages.append({"role": "user", "content": pergunta})
    st.rerun()


def render_perguntas_pre_definidas(prefixo: str = "quick") -> None:
    """Renderiza perguntas rápidas em abas por categoria.

    O prefixo evita conflito de chaves quando o mesmo componente aparece
    no corpo da página e também na barra lateral.
    """
    categorias = list(PERGUNTAS_PRE_DEFINIDAS.keys())
    abas = st.tabs(categorias)

    for idx_categoria, categoria in enumerate(categorias):
        perguntas = PERGUNTAS_PRE_DEFINIDAS[categoria]

        with abas[idx_categoria]:
            st.caption("Clique em uma pergunta para consultar a Minerva automaticamente.")

            for idx_pergunta, pergunta in enumerate(perguntas):
                chave = f"{prefixo}_{idx_categoria}_{idx_pergunta}"

                if st.button(pergunta, key=chave, use_container_width=True):
                    adicionar_pergunta_rapida(pergunta)


def gerar_txt_historico() -> bytes:
    """Gera exportação simples do histórico atual em TXT."""
    linhas = ["Histórico da sessão - Minerva AI", ""]

    for msg in st.session_state.get("messages", []):
        papel = "Minerva" if msg.get("role") == "assistant" else "Usuário"
        conteudo = msg.get("content", "").strip()

        linhas.append(f"[{papel}] {conteudo}")
        linhas.append("")

    return "\n".join(linhas).encode("utf-8")




# =============================================================================
# COMPONENTES CLEAN DE PERGUNTAS FREQUENTES
# =============================================================================
def obter_lista_perguntas_flat() -> list[str]:
    """Converte PERGUNTAS_PRE_DEFINIDAS em lista única e limpa."""
    perguntas: list[str] = []

    try:
        for _, itens in PERGUNTAS_PRE_DEFINIDAS.items():
            perguntas.extend(itens)
    except Exception:
        perguntas = [
            "Me mostre o calendário acadêmico de 2026",
            "Quais são as regras de estágio?",
            "Quero saber o regulamento do TCC",
            "Qual é o cardápio do RU?",
        ]

    # Remove duplicadas preservando ordem.
    vistas = set()
    unicas = []

    for pergunta in perguntas:
        if pergunta not in vistas:
            vistas.add(pergunta)
            unicas.append(pergunta)

    return unicas


def render_consulta_rapida_clean(prefixo: str = "clean") -> None:
    """Renderiza perguntas frequentes em selectbox, evitando muitos botões.

    Também usa prefixo único para evitar conflito de keys.
    """
    global _MINERVA_RENDER_COUNTER
    _MINERVA_RENDER_COUNTER += 1
    prefixo = f"{prefixo}_{_MINERVA_RENDER_COUNTER}"
    perguntas = obter_lista_perguntas_flat()

    escolha = st.selectbox(
        "Perguntas frequentes",
        options=["Selecione uma pergunta pronta..."] + perguntas,
        key=f"{prefixo}_select_pergunta",
    )

    col_a, col_b = st.columns([1, 3])

    with col_a:
        consultar = st.button(
            "Consultar",
            key=f"{prefixo}_btn_consultar",
            use_container_width=True,
        )

    with col_b:
        st.caption("Use uma pergunta pronta ou digite sua dúvida no campo principal.")

    if consultar and escolha != "Selecione uma pergunta pronta...":
        st.session_state.messages.append({"role": "user", "content": escolha})
        st.rerun()


def render_historico_clean() -> None:
    """Mostra histórico de forma compacta e recolhida."""
    perguntas = [
        msg.get("content", "")
        for msg in st.session_state.get("messages", [])
        if msg.get("role") == "user"
    ]

    if not perguntas:
        st.caption("Sem perguntas nesta sessão.")
        return

    for idx, pergunta in enumerate(perguntas[-6:], start=1):
        st.markdown(
            f"<div class='history-item'><strong>{idx}.</strong> {pergunta}</div>",
            unsafe_allow_html=True,
        )




_MINERVA_RENDER_COUNTER = 0

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
    """Mostra as últimas perguntas como atalhos clicáveis."""
    perguntas = obter_perguntas_usuario()

    if not perguntas:
        return

    recentes = perguntas[-6:]

    for idx, pergunta in enumerate(reversed(recentes)):
        label = pergunta.strip()

        if len(label) > 48:
            label = label[:45] + "..."

        if st.button(
            label,
            key=f"hist_v2_{idx}_{abs(hash(pergunta))}",
            use_container_width=True,
        ):
            enviar_pergunta_minerva(pergunta)



def render_cards_categorias(prefixo: str = "home") -> None:
    """Renderiza categorias compactas e perguntas sugeridas.

    Melhorias:
    - elimina duplicação visual;
    - destaca categoria selecionada;
    - usa keys exclusivas;
    - reduz altura da página.
    """
    global _MINERVA_RENDER_COUNTER

    _MINERVA_RENDER_COUNTER += 1
    render_id = _MINERVA_RENDER_COUNTER

    if "categoria_minerva_ativa" not in st.session_state:
        st.session_state.categoria_minerva_ativa = "Calendário"

    categorias = list(CATEGORIAS_MINERVA.keys())

    st.markdown(
        '<div class="minerva-v2-section-title">'
        'Acessos rápidos'
        '</div>',
        unsafe_allow_html=True,
    )

    primeira_linha = categorias[:4]
    segunda_linha = categorias[4:]

    if primeira_linha:
        cols = st.columns(len(primeira_linha))

        for idx, (col, categoria) in enumerate(
            zip(cols, primeira_linha)
        ):
            ativo = (
                st.session_state.categoria_minerva_ativa
                == categoria
            )

            with col:
                if st.button(
                    categoria,
                    key=f"{prefixo}_{render_id}_cat_a_{idx}",
                    use_container_width=True,
                    type="primary" if ativo else "secondary",
                ):
                    st.session_state.categoria_minerva_ativa = categoria
                    st.rerun()

    if segunda_linha:
        cols = st.columns(len(segunda_linha))

        for idx, (col, categoria) in enumerate(
            zip(cols, segunda_linha)
        ):
            ativo = (
                st.session_state.categoria_minerva_ativa
                == categoria
            )

            with col:
                if st.button(
                    categoria,
                    key=f"{prefixo}_{render_id}_cat_b_{idx}",
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
                key=f"{prefixo}_{render_id}_q_{idx}",
                use_container_width=True,
            ):
                enviar_pergunta_minerva(pergunta)



# =============================================================================
# MODELO LOCAL / FALLBACK
# =============================================================================
def consultar_modelo_local(pergunta: str) -> str:
    """Consulta modelo local compatível com /v1/chat/completions.

    O prompt foi ajustado para não inventar normas, datas ou prazos quando
    não houver documento oficial localizado.
    """
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é a Minerva, assistente virtual da FCT/UFPA. "
                    "Responda em português, com clareza e objetividade. "
                    "Se a pergunta depender de documento oficial não localizado, "
                    "informe que não encontrou base documental suficiente. "
                    "Não invente normas, datas, prazos, requisitos, artigos ou procedimentos acadêmicos."
                ),
            },
            {"role": "user", "content": pergunta},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }

    try:
        response = http_session.post(LLM_API_URL, json=payload, timeout=12)

        if response.status_code != 200:
            logger.warning(
                "Modelo retornou status %s: %s",
                response.status_code,
                response.text,
            )
            return (
                "Não localizei registros correspondentes para esta solicitação. "
                "Tente simplificar os termos buscados."
            )

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as exc:
        logger.exception("Erro ao consultar modelo local: %s", exc)
        return (
            "No momento, não foi possível consultar a base assistida. "
            "Tente novamente mais tarde ou reformule sua pergunta."
        )


# =============================================================================
# ESTADO DE SESSÃO
# =============================================================================
# Cada navegador/sessão recebe um ID próprio.
# Isso impede que conversas de usuários diferentes se misturem.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

inicializar_banco()

if "messages" not in st.session_state:
    st.session_state.messages = []

    registros_passados = carregar_historico_sessao()

    for pergunta, resposta in registros_passados:
        st.session_state.messages.append({"role": "user", "content": pergunta})

        nome_arq, texto_raw = buscar_contexto_e_arquivo(pergunta)
        msg_dict = {"role": "assistant", "content": resposta}

        if nome_arq:
            texto_formatado = formatar_documento_para_download(texto_raw, nome_arq)
            msg_dict["download_file"] = nome_arq
            msg_dict["exibir_extensao"] = usuario_pediu_formato(pergunta)
            msg_dict["pdf_bytes"] = obter_binario_pdf(nome_arq)
            msg_dict["docx_bytes"] = gerar_docx(texto_formatado)

        st.session_state.messages.append(msg_dict)


# =============================================================================
# INTERFACE
# =============================================================================
with st.sidebar:
    st.markdown(
        """
        <div class="minerva-v2-sidebar-brand">
            <strong>Minerva AI</strong>
            <span>FCT/UFPA</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    perguntas_usuario = obter_perguntas_usuario()

    if st.button(
        "＋ Nova conversa",
        key="sidebar_v2_nova_conversa",
        use_container_width=True,
        type="primary",
    ):
        if limpar_historico_banco():
            st.session_state.messages = []
            st.session_state.categoria_minerva_ativa = "Calendário"
            st.rerun()

    # Histórico aparece somente quando existe.
    if perguntas_usuario:

        st.markdown(
            '<div class="minerva-v2-history-title">'
            'Histórico recente'
            '</div>',
            unsafe_allow_html=True,
        )

        render_historico_clicavel()

        st.markdown("---")

        st.download_button(
            "Exportar histórico",
            data=gerar_txt_historico(),
            file_name="historico_minerva.txt",
            mime="text/plain",
            use_container_width=True,
            key="sidebar_v2_export",
        )

    st.markdown("---")

    st.caption(
        "Assistente acadêmica baseada em documentos "
        "institucionais da FCT/UFPA."
    )




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
        avatar = "🏫" if msg["role"] == "assistant" else "👤"

        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

            if msg["role"] == "assistant" and "download_file" in msg:
                render_downloads(msg, idx)



# CABECALHO NATIVO MINERVA V4
# Usa componentes Streamlit para evitar HTML aparecendo como texto.
_header_logo, _header_texto = st.columns([1, 12], gap="small")

with _header_logo:
    st.image(
        UFPA_LOGO_URL,
        width=56,
    )

with _header_texto:
    st.markdown("## Minerva AI")
    st.caption("Orientação acadêmica da FCT/UFPA")

st.divider()
# FIM CABECALHO NATIVO MINERVA V4


# =============================================================================
# ÁREA PRINCIPAL UX V2
# =============================================================================

# -------------------------------------------------------------------------
# 1. Introdução curta
# -------------------------------------------------------------------------
if len(st.session_state.messages) == 0:

    st.markdown(
        """
        <div class="minerva-v2-intro">
            <h2>Olá, sou a Minerva.</h2>
            <p>
                Consulte informações acadêmicas da FCT/UFPA
                ou o cardápio publicado pela PROAES.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------------------------------------------------------------
# 2. Campo principal de pergunta
# -------------------------------------------------------------------------
st.markdown(
    '<div class="minerva-v2-ask-label">'
    'Como posso ajudar?'
    '</div>',
    unsafe_allow_html=True,
)

with st.form(
    "minerva_v2_form_pergunta",
    clear_on_submit=True,
    border=False,
):

    pergunta_digitada = st.text_input(
        "Pergunta",
        placeholder="Ex.: Quais são as regras de estágio?",
        label_visibility="collapsed",
    )

    enviar_pergunta = st.form_submit_button(
        "Enviar pergunta",
        use_container_width=True,
        type="primary",
    )

if enviar_pergunta and pergunta_digitada.strip():

    st.session_state.messages.append(
        {
            "role": "user",
            "content": pergunta_digitada.strip(),
        }
    )

    st.rerun()


# -------------------------------------------------------------------------
# 3. Histórico visual da conversa
# -------------------------------------------------------------------------
if st.session_state.messages:
    render_chat_history()


# -------------------------------------------------------------------------
# 4. Categorias
# -------------------------------------------------------------------------
if len(st.session_state.messages) == 0:

    render_cards_categorias(
        prefixo="home_v2"
    )

else:

    with st.expander(
        "Sugestões de perguntas",
        expanded=False,
    ):
        render_cards_categorias(
            prefixo="chat_v2"
        )



# =============================================================================
# PROCESSAMENTO DA PERGUNTA
# =============================================================================
def processar_pergunta(query_executar: str) -> dict[str, Any]:
    """Processa a última pergunta e devolve a mensagem do assistente."""
    query_lc = query_executar.lower().strip()

    if query_lc in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "ajuda"]:
        resposta = (
            "Olá. Posso ajudar a localizar documentos acadêmicos da FCT/UFPA. "
            "Você pode perguntar sobre calendário, estágio, TCC, regimento, graduação ou atividades complementares."
        )

        salvar_no_historico(query_executar, resposta)

        return {"role": "assistant", "content": resposta}

    if eh_pergunta_cardapio(query_executar):
        resposta = responder_cardapio_proaes(query_executar)
        salvar_no_historico(query_executar, resposta)
        return {"role": "assistant", "content": resposta}

    nome_arq, texto_raw = buscar_contexto_e_arquivo(query_executar)

    if nome_arq:
        resposta = montar_resposta_documento(nome_arq, query_executar)
        if "Fonte:" not in resposta:
            resposta = f"{resposta}\n\n---\nFonte: `{nome_arq}`"
        texto_formatado = formatar_documento_para_download(texto_raw, nome_arq)

        salvar_no_historico(query_executar, resposta)

        return {
            "role": "assistant",
            "content": resposta,
            "download_file": nome_arq,
            "exibir_extensao": usuario_pediu_formato(query_executar),
            "pdf_bytes": obter_binario_pdf(nome_arq),
            "docx_bytes": gerar_docx(texto_formatado),
        }

    with st.status("🔍 Consultando base assistida...", expanded=False) as status:
        resposta = consultar_modelo_local(query_executar)
        status.update(label="Concluído", state="complete")

    salvar_no_historico(query_executar, resposta)

    return {"role": "assistant", "content": resposta}


if len(st.session_state.messages) >= 1 and st.session_state.messages[-1]["role"] == "user":
    ultima_pergunta = st.session_state.messages[-1]["content"]

    with st.chat_message("assistant", avatar="🏫"):
        nova_msg = processar_pergunta(ultima_pergunta)

    st.session_state.messages.append(nova_msg)
    st.rerun()
