
from __future__ import annotations
# MINERVA_PRIORITY_ROUTER_IMPORT_BEGIN
try:
    from .minerva_priority_router import priority_answer
except (ImportError, ValueError):
    from minerva_priority_router import priority_answer
# MINERVA_PRIORITY_ROUTER_IMPORT_END

from minerva_hybrid import responder_minerva
import uuid

import streamlit as st

# MINERVA_HISTORY_IMPORT_BEGIN
try:
    from .minerva_history import (
        normalizar_mensagem_historico,
        mensagem_role,
        mensagem_content,
    )
except (ImportError, ValueError):
    from minerva_history import (
        normalizar_mensagem_historico,
        mensagem_role,
        mensagem_content,
    )
# MINERVA_HISTORY_IMPORT_END

# MINERVA_UI_IMPORT_BEGIN
try:
    from .ui import (
        aplicar_css,
        normalizar_historico_session_state,
        iniciar_nova_conversa,
        obter_perguntas_usuario,
        gerar_txt_historico,
        render_lista_conversas,
        render_cards_categorias,
        render_chat_history,
    )
except (ImportError, ValueError):
    from ui import (
        aplicar_css,
        normalizar_historico_session_state,
        iniciar_nova_conversa,
        obter_perguntas_usuario,
        gerar_txt_historico,
        render_lista_conversas,
        render_cards_categorias,
        render_chat_history,
    )
# MINERVA_UI_IMPORT_END


# Normaliza automaticamente históricos antigos.
normalizar_historico_session_state()











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
# CONFIGURAÇÕES SEGURAS E LOGGING
# =============================================================================
# MINERVA_CONFIG_IMPORT_BEGIN
try:
    from .config import UFPA_LOGO_URL
except (ImportError, ValueError):
    from config import UFPA_LOGO_URL
# MINERVA_CONFIG_IMPORT_END


# =============================================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# =============================================================================
# page_icon usa o mesmo logo do cabeçalho (UFPA_LOGO_URL, definido acima) em vez
# do emoji genérico 🏫 — antes a aba do navegador não tinha identidade visual
# com o resto da aplicação.
st.set_page_config(
    page_title="Minerva - FCT/UFPA",
    layout="centered",
    page_icon=UFPA_LOGO_URL,
    initial_sidebar_state="expanded",
)


# =============================================================================
# CSS DA INTERFACE
# =============================================================================
aplicar_css()


# MINERVA_DB_IMPORT_BEGIN
try:
    from .db import (
        db_pool,
        inicializar_banco,
        salvar_no_historico,
        carregar_historico_conversa,
        listar_conversas_dispositivo,
        salvar_avaliacao,
    )
except (ImportError, ValueError):
    from db import (
        db_pool,
        inicializar_banco,
        salvar_no_historico,
        carregar_historico_conversa,
        listar_conversas_dispositivo,
        salvar_avaliacao,
    )
# MINERVA_DB_IMPORT_END

# MINERVA_AVALIACAO_IMPORT_BEGIN
try:
    from .minerva_avaliacao import render_formulario_avaliacao
except (ImportError, ValueError):
    from minerva_avaliacao import render_formulario_avaliacao
# MINERVA_AVALIACAO_IMPORT_END


# =============================================================================
# DOCUMENTOS E DOWNLOADS
# =============================================================================
# MINERVA_DOCUMENTS_IMPORT_BEGIN
try:
    from .documents import (
        obter_binario_pdf,
        formatar_documento_para_download,
        gerar_docx,
        buscar_contexto_e_arquivo,
        usuario_pediu_formato,
    )
except (ImportError, ValueError):
    from documents import (
        obter_binario_pdf,
        formatar_documento_para_download,
        gerar_docx,
        buscar_contexto_e_arquivo,
        usuario_pediu_formato,
    )
# MINERVA_DOCUMENTS_IMPORT_END


# =============================================================================
# MODELO LOCAL / FALLBACK RESTRITO À FCT/UFPA
# =============================================================================
# MINERVA_PROMPTS_IMPORT_BEGIN
try:
    from .prompts import (
        pergunta_menciona_instituicao_externa,
        consultar_modelo_local,
    )
except (ImportError, ValueError):
    from prompts import (
        pergunta_menciona_instituicao_externa,
        consultar_modelo_local,
    )
# MINERVA_PROMPTS_IMPORT_END

# =============================================================================
# ESTADO DE SESSÃO
# =============================================================================
# Cada navegador/sessão recebe um ID próprio.
# Isso impede que conversas de usuários diferentes se misturem.
#
# O session_id é espelhado em st.query_params ("sid"): st.session_state por
# si só reseta a cada reload de página (nova conexão WebSocket = novo estado
# em branco), então sem isso "carregar_historico_sessao()" abaixo quase nunca
# encontrava nada — um F5 gerava um session_id novo antes mesmo de checar o
# banco. Guardar o id na URL faz o histórico sobreviver a reloads dentro do
# mesmo link/aba, sem precisar de cookies ou login.
if "session_id" not in st.session_state:
    sid_da_url = st.query_params.get("sid")

    if sid_da_url:
        try:
            uuid.UUID(sid_da_url)
            st.session_state.session_id = sid_da_url
        except ValueError:
            st.session_state.session_id = None

    if not st.session_state.get("session_id"):
        st.session_state.session_id = str(uuid.uuid4())

    st.query_params["sid"] = st.session_state.session_id

# Conversa ativa dentro da sessão/dispositivo: um dispositivo pode ter
# várias conversas (ver listar_conversas_dispositivo em db.py e a lista na
# sidebar). Mesmo padrão de persistência do session_id acima, espelhada em
# st.query_params ("cid") pra sobreviver a reloads.
if "conversa_id" not in st.session_state:
    cid_da_url = st.query_params.get("cid")

    if cid_da_url:
        try:
            uuid.UUID(cid_da_url)
            st.session_state.conversa_id = cid_da_url
        except ValueError:
            st.session_state.conversa_id = None

    if not st.session_state.get("conversa_id"):
        st.session_state.conversa_id = str(uuid.uuid4())

    st.query_params["cid"] = st.session_state.conversa_id

inicializar_banco()

if "messages" not in st.session_state:
    st.session_state.messages = []

    registros_passados = carregar_historico_conversa(st.session_state.conversa_id)

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

        st.session_state.messages.append(normalizar_mensagem_historico(msg_dict, role_padrao="assistant"))


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

    if st.button(
        "＋ Nova conversa",
        key="sidebar_v2_nova_conversa",
        use_container_width=True,
        type="primary",
    ):
        # Não apaga nada do banco: só inicia uma conversa nova. A conversa
        # anterior fica intacta e passa a aparecer na lista abaixo.
        iniciar_nova_conversa()
        st.rerun()

    conversas = listar_conversas_dispositivo()

    # Lista de conversas aparece somente quando existe alguma.
    if conversas:

        st.markdown(
            '<div class="minerva-v2-history-title">'
            'Conversas'
            '</div>',
            unsafe_allow_html=True,
        )

        render_lista_conversas(conversas)

        st.markdown("---")

    perguntas_usuario = obter_perguntas_usuario()

    if perguntas_usuario:

        st.download_button(
            "Exportar histórico",
            data=gerar_txt_historico(),
            file_name="historico_minerva.txt",
            mime="text/plain",
            use_container_width=True,
            key="sidebar_v2_export",
        )

    st.markdown("---")

    # Alterna entre o chat e o formulário de avaliação (minerva_avaliacao.py).
    if st.session_state.get("modo_avaliacao"):
        if st.button(
            "← Voltar ao chat",
            key="sidebar_v2_voltar_chat",
            use_container_width=True,
        ):
            st.session_state.modo_avaliacao = False
            st.rerun()
    elif st.button(
        "📝 Avaliar a Minerva",
        key="sidebar_v2_avaliacao",
        use_container_width=True,
    ):
        st.session_state.modo_avaliacao = True
        st.rerun()

    st.markdown("---")

    st.caption(
        "**M.I.N.E.R.V.A.** – Módulo Inteligente de Navegação e "
        "Ensino de Recursos Virtuais Acadêmicos. Assistente "
        "acadêmica baseada em documentos institucionais da FCT/UFPA."
    )




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
# MODO AVALIAÇÃO
# =============================================================================
# No modo avaliação, o formulário substitui a área do chat inteira;
# st.stop() impede que o restante do script (intro, histórico, chat_input,
# processamento) seja renderizado — a sidebar acima continua visível.
if st.session_state.get("modo_avaliacao"):
    render_formulario_avaliacao(
        salvar_func=salvar_avaliacao,
        session_id=st.session_state.session_id,
    )
    st.stop()


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
# 2. Histórico visual da conversa
# -------------------------------------------------------------------------
if st.session_state.messages:
    render_chat_history()


# -------------------------------------------------------------------------
# 3. Categorias
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


# -------------------------------------------------------------------------
# 4. Campo de pergunta — fixo no rodapé e com rolagem automática, nativos
#    do st.chat_input (substitui o antigo st.form + text_input do topo).
# -------------------------------------------------------------------------
pergunta_digitada = st.chat_input(
    "Faça sua pergunta"
)

if pergunta_digitada and pergunta_digitada.strip():

    st.session_state.messages.append(
        {
            "role": "user",
            "content": pergunta_digitada.strip(),
        }
    )

    st.rerun()



# =============================================================================
# PROCESSAMENTO DA PERGUNTA
# =============================================================================
def processar_pergunta(pergunta, stream_area=None):
    """
    Processa perguntas da Minerva usando camada institucional FCT/UFPA.

    stream_area (st.empty() opcional): quando presente, a resposta do RAG
    genérico é exibida token a token ali enquanto o modelo gera (streaming
    SSE — ver consultar_modelo_local). As rotas fixas continuam respondendo
    de uma vez, já que são instantâneas.

    Passo a passo (a primeira camada que responder encerra o fluxo):

    1. ROTAS FIXAS — priority_answer() (minerva_priority_router.py) resolve
       deterministicamente calendário, cardápio do RU, TCC, estágio,
       contatos etc., incluindo as camadas de fatos básicos
       (minerva_basic_facts.py) e dataset manual (minerva_dataset.py).
       Resposta instantânea, sem tocar no LLM.
    2. BARREIRA PRÉ-GERAÇÃO — pergunta_menciona_instituicao_externa()
       bloqueia, antes de qualquer busca, pergunta explicitamente dirigida
       a outra universidade (UFxx ≠ UFPA, FCT de Lisboa...).
    3. CONEXÃO — pega uma conexão do pool (db_pool); sem banco, o RAG
       degrada graciosamente para o fallback genérico.
    4. RAG GENÉRICO — responder_minerva() (minerva_hybrid.py) faz a busca
       híbrida (léxica + semântica + fusão RRF) e chama o modelo local
       via consultar_modelo_local() — ver o passo a passo detalhado no
       docstring de responder_minerva.
    5. DEVOLUÇÃO DA CONEXÃO — putconn() no finally, senão o pool esgota.
    """
    # MINERVA_PRIORITY_ROUTER_GUARD_BEGIN
    _minerva_priority_result = priority_answer(pergunta)
    if _minerva_priority_result is not None:
        return _minerva_priority_result
    # MINERVA_PRIORITY_ROUTER_GUARD_END

    # Checagem de instituição externa feita aqui, sobre a pergunta CRUA do
    # usuário — e não dentro de consultar_modelo_local, que só recebe o
    # prompt já montado (pergunta + contexto + instruções institucionais).
    if pergunta_menciona_instituicao_externa(pergunta):
        return (
            "Meu escopo institucional está restrito à "
            "**Faculdade de Computação e Telecomunicações (FCT)** da "
            "**Universidade Federal do Pará (UFPA)**. "
            "Não utilizo informações de outras universidades para responder "
            "como se fossem dados da UFPA."
        )

    # Bug real: este trecho procurava por get_connection/conectar_postgres/
    # conectar_banco, nenhuma das quais existe neste módulo (main.py usa
    # db_pool + executar_query). "conn" nunca era preenchido, então
    # buscar_em_documentos_postgres(conn=None, ...) sempre devolvia [] e a
    # Minerva caía direto no fallback genérico — nunca chegava a consultar
    # o banco nem a chamar o modelo local, para nenhuma pergunta fora das
    # rotas fixas do priority_router.
    conn = None

    try:
        if db_pool:
            conn = db_pool.getconn()
    except Exception:
        conn = None

    def llm_func(prompt):
        if stream_area is None:
            return consultar_modelo_local(prompt)

        # O callback recebe o texto acumulado pronto pra exibir; o "▌" no
        # fim imita o cursor de digitação enquanto a geração não termina.
        return consultar_modelo_local(
            prompt,
            on_chunk=lambda texto: stream_area.markdown(texto + " ▌"),
        )

    # try/finally: sem ele, uma exceção em responder_minerva vazava a
    # conexão (nunca voltava ao pool) — com DB_POOL_MAX=10, dez erros
    # seguidos esgotariam o pool e derrubariam o app inteiro.
    try:
        return responder_minerva(
            pergunta=pergunta,
            conn=conn,
            llm_func=llm_func
        )
    finally:
        if conn:
            try:
                db_pool.putconn(conn)
            except Exception:
                pass


if len(st.session_state.messages) >= 1 and mensagem_role(st.session_state.messages[-1]) == "user":
    ultima_pergunta = mensagem_content(st.session_state.messages[-1])

    with st.chat_message("assistant", avatar="🏫"):
        # Área onde a resposta aparece token a token durante a geração
        # (preenchida pelo on_chunk em llm_func). O spinner cobre a fase
        # muda (busca no banco + leitura do prompt pelo modelo); assim que
        # o primeiro token chega, o texto começa a crescer abaixo dele.
        stream_area = st.empty()

        with st.spinner("Consultando fontes oficiais da FCT/UFPA..."):
            nova_msg = processar_pergunta(ultima_pergunta, stream_area=stream_area)

        # O st.rerun() abaixo redesenha tudo via render_chat_history();
        # limpar aqui evita a resposta duplicada (parcial + final) no
        # instante entre o fim da geração e o rerun.
        stream_area.empty()

    salvar_no_historico(st.session_state.conversa_id, ultima_pergunta, mensagem_content(nova_msg))

    st.session_state.messages.append(normalizar_mensagem_historico(nova_msg, role_padrao="assistant"))
    st.rerun()
