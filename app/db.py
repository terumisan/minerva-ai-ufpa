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

    A coluna session_id identifica o navegador/dispositivo. A coluna
    conversa_id agrupa mensagens dentro de uma mesma conversa (um
    session_id pode ter várias conversas — ver listar_conversas_dispositivo).
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

    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS conversa_id TEXT;",
        commit=True,
    )

    # Backfill: antes desta mudança, um session_id inteiro já era uma única
    # conversa contínua — agrupar as linhas antigas por session_id preserva
    # esse histórico como "uma conversa por sessão antiga" sem perder nada.
    executar_query(
        "UPDATE historico_minerva SET conversa_id = session_id WHERE conversa_id IS NULL;",
        commit=True,
    )

    # NULL = sem título customizado (cai no fallback da primeira pergunta em
    # listar_conversas_dispositivo) — sem necessidade de backfill.
    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS titulo_personalizado TEXT;",
        commit=True,
    )

    # Qual camada respondeu (rota fixa, dataset, RAG genérico, barreira
    # institucional) e quanto tempo levou. NULL = pergunta salva antes
    # desta coluna existir (sem backfill possível — a informação não foi
    # capturada na época). Existe pra medir cobertura de rotas e latência
    # de forma automática, em vez de varredura manual do histórico (ver
    # conversa) toda vez que se quer saber o que ainda cai no RAG lento.
    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS rota TEXT;",
        commit=True,
    )

    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS latencia_ms INTEGER;",
        commit=True,
    )

    # 'positivo' | 'negativo' | NULL (sem feedback). Um clique no 👍/👎
    # abaixo de cada resposta (ui.py) faz UPDATE nesta coluna pelo id da
    # linha — ver registrar_feedback().
    executar_query(
        "ALTER TABLE historico_minerva ADD COLUMN IF NOT EXISTS feedback TEXT;",
        commit=True,
    )

    # Respostas do formulário de avaliação (minerva_avaliacao.py). Colunas
    # fixas só para o que se consulta direto (score SUS, curso); o restante
    # do formulário vai íntegro no JSONB — adicionar pergunta nova ao
    # formulário não exige migração.
    executar_query(
        """
        CREATE TABLE IF NOT EXISTS avaliacoes_minerva (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            curso TEXT,
            sus_score NUMERIC,
            respostas JSONB
        );
        """,
        commit=True,
    )


def salvar_no_historico(
    conversa_id: str,
    pergunta: str,
    resposta: str,
    rota: str | None = None,
    latencia_ms: int | None = None,
) -> int | None:
    """Salva pergunta e resposta na conversa indicada, dentro da sessão atual.

    rota/latencia_ms são opcionais (default None) pra não quebrar nenhuma
    chamada existente que ainda não tenha essa informação disponível.

    Devolve o id da linha inserida (RETURNING) — usado em main.py pra
    anexar "historico_id" na mensagem em session_state, permitindo que os
    botões de feedback/regenerar (ui.py) referenciem a linha exata sem
    precisar casar por texto. None se a query falhar (ver executar_query).
    """
    resultado = executar_query(
        """
        INSERT INTO historico_minerva
            (session_id, conversa_id, pergunta, resposta, rota, latencia_ms)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        params=(
            st.session_state.session_id,
            conversa_id,
            pergunta,
            resposta,
            rota,
            latencia_ms,
        ),
        fetch=True,
        commit=True,
    )

    return resultado[0][0] if resultado else None


def carregar_historico_conversa(conversa_id: str) -> list[tuple[int, str, str, str | None]]:
    """Carrega o histórico persistido de uma conversa específica.

    Filtra também por session_id: um dispositivo não pode carregar uma
    conversa de outro, mesmo que adivinhe o conversa_id.

    Devolve (id, pergunta, resposta, feedback) — id e feedback alimentam
    os botões de ação por mensagem (ui.py, render_chat_history).
    """
    registros = executar_query(
        """
        SELECT id, pergunta, resposta, feedback
        FROM historico_minerva
        WHERE session_id = %s AND conversa_id = %s
        ORDER BY id ASC;
        """,
        params=(st.session_state.session_id, conversa_id),
        fetch=True,
    )

    return registros or []


def registrar_feedback(historico_id: int, feedback: str) -> None:
    """Grava 👍/👎 numa resposta específica.

    Sem filtro por session_id de propósito: historico_id já é a chave
    primária da linha (só existe pra quem já viu a resposta renderizada
    na própria sessão — não é um id adivinhável/exposto em URL).
    """
    executar_query(
        "UPDATE historico_minerva SET feedback = %s WHERE id = %s;",
        params=(feedback, historico_id),
        commit=True,
    )


def listar_conversas_dispositivo(limite: int = 15) -> list[tuple[str, str, Any]]:
    """Lista as conversas da sessão atual, mais recente primeiro.

    Cada item é (conversa_id, titulo, ultima_atividade). O título é o
    titulo_personalizado (ver renomear_conversa) quando existir; senão cai
    na primeira pergunta da conversa. Ordenação por atividade mais recente
    não muda com o título — renomear não deve "subir" a conversa na lista.
    """
    registros = executar_query(
        """
        SELECT
            conversa_id,
            COALESCE(
                MAX(titulo_personalizado),
                (ARRAY_AGG(pergunta ORDER BY id ASC))[1]
            ) AS titulo,
            MAX(data_hora) AS ultima_atividade
        FROM historico_minerva
        WHERE session_id = %s AND conversa_id IS NOT NULL
        GROUP BY conversa_id
        ORDER BY ultima_atividade DESC
        LIMIT %s;
        """,
        params=(st.session_state.session_id, limite),
        fetch=True,
    )

    return registros or []


def renomear_conversa(conversa_id: str, novo_titulo: str) -> None:
    """Define um título customizado para a conversa (sobrepõe a 1ª pergunta)."""
    executar_query(
        """
        UPDATE historico_minerva
        SET titulo_personalizado = %s
        WHERE session_id = %s AND conversa_id = %s;
        """,
        params=(novo_titulo, st.session_state.session_id, conversa_id),
        commit=True,
    )


def excluir_conversa(conversa_id: str) -> None:
    """Remove uma conversa específica do histórico da sessão atual.

    Mesmo filtro duplo de segurança de carregar_historico_conversa: um
    dispositivo não pode excluir conversa de outro, mesmo adivinhando o id.
    """
    executar_query(
        """
        DELETE FROM historico_minerva
        WHERE session_id = %s AND conversa_id = %s;
        """,
        params=(st.session_state.session_id, conversa_id),
        commit=True,
    )


def salvar_avaliacao(session_id: str, registro: dict) -> None:
    """Persiste uma resposta do formulário de avaliação (minerva_avaliacao.py)."""
    try:
        from minerva_avaliacao import registro_para_json
    except ImportError:
        from .minerva_avaliacao import registro_para_json

    executar_query(
        """
        INSERT INTO avaliacoes_minerva (session_id, curso, sus_score, respostas)
        VALUES (%s, %s, %s, %s);
        """,
        params=(
            session_id,
            registro.get("curso"),
            registro.get("sus_score"),
            registro_para_json(registro),
        ),
        commit=True,
    )
