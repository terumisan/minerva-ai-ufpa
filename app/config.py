from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import streamlit as st

# ======================================================================
# MINERVA AI
# Configurações centrais: credenciais, endereços de serviços externos e
# logging (aplicado uma única vez aqui, já que este é o primeiro módulo
# importado por main.py e pelos demais módulos que precisam de "logger").
# ======================================================================

# O logging registra falhas técnicas no console/container sem exibir stack
# trace para o usuário final.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("minerva")


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
DB_PASSWORD = get_config("DB_PASSWORD", "")

DB_POOL_MIN = int(get_config("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(get_config("DB_POOL_MAX", "10"))

LLM_API_URL = get_config(
    "LLM_API_URL",
    "http://ufpa_rag_llm:8002/v1/chat/completions",
)

DOCUMENTOS_DIR = Path(str(get_config("DOCUMENTOS_DIR", "documentos")))

UFPA_LOGO_URL = get_config(
    "UFPA_LOGO_URL",
    str(Path(__file__).parent / "assets" / "logo-ufpa.png"),
)
