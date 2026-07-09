from __future__ import annotations

from typing import Any

import psycopg2
import streamlit as st
from psycopg2 import pool

# MINERVA_DB_CONFIG_IMPORT_BEGIN
try:
    from .config import (
        DB_HOST,
        DB_PORT,
        DB_NAME,
        DB_USER,
        DB_PASSWORD,
        DB_POOL_MIN,
        DB_POOL_MAX,
        logger,
    )
except (ImportError, ValueError):
    from config import (
        DB_HOST,
        DB_PORT,
        DB_NAME,
        DB_USER,
        DB_PASSWORD,
        DB_POOL_MIN,
        DB_POOL_MAX,
        logger,
    )
# MINERVA_DB_CONFIG_IMPORT_END


# ======================================================================
# MINERVA AI
# Acesso ao Postgres: pool de conexões e histórico de conversa.
# ======================================================================


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


db_pool = get_db_pool()


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
