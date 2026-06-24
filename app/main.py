import streamlit as st
import requests
import psycopg2
from psycopg2 import pool
import re
import os
from datetime import datetime

# Configuração de Layout da Página
st.set_page_config(
    page_title="Minerva - FCT/UFPA",
    layout="centered",
    page_icon="🏫",
    initial_sidebar_state="expanded"
)

# CSS para Interface Clean, Moderna e Botões de Ação
st.markdown("""
    <style>
    .logo-container { display: flex; justify-content: center; align-items: center; padding-top: 10px; margin-bottom: 5px; }
    .logo-img { width: 140px !important; height: auto !important; object-fit: contain; }
    .chat-header { text-align: center; padding: 0px 0 10px 0; }
    .chat-header h1 { font-family: 'Inter', sans-serif; font-weight: 800; background: linear-gradient(45deg, #1E40AF, #3B82F6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 5px 0; }
    .chat-header p { color: #6B7280; font-size: 1rem; }
    .stSidebar { background-color: #0F172A !important; }
    .stSidebar h3, .stSidebar h4, .stSidebar p, .stSidebar span { color: #F8FAFC !important; }
    .explanation-box { margin-bottom: 15px; line-height: 1.6; }
    
    /* Customização dos botões de ação rápida */
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
""", unsafe_allow_html=True)

# ==========================================
# ⚡ OTIMIZAÇÕES DE PERFORMANCE (CACHES)
# ==========================================

@st.cache_resource
def get_http_session():
    return requests.Session()

http_session = get_http_session()

@st.cache_resource
def get_db_pool():
    try:
        return psycopg2.pool.SimpleConnectionPool(
            1, 10,
            host="ufpa_rag_db", database="ufpa_rag", user="admin", password="ufpa_senha_123"
        )
    except Exception as e:
        print(f"Erro ao inicializar Pool de Banco de Dados: {e}")
        return None

db_pool = get_db_pool()

def executar_query(sql, params=None, fetch=False, commit=False):
    if not db_pool: return None
    conn = db_pool.getconn()
    resultado = None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if fetch:
            resultado = cur.fetchall()
        if commit:
            conn.commit()
        cur.close()
    except Exception as e:
        print(f"Erro na query: {e}")
    finally:
        db_pool.putconn(conn)
    return resultado

# ==========================================
# 🔧 GERENCIADOR DE ARQUIVOS E FORMATOS
# ==========================================

def obter_binario_pdf(nome_arquivo):
    caminhos_possiveis = [
        os.path.join("documentos", nome_arquivo),
        os.path.join("..", "documentos", nome_arquivo),
        os.path.join("/app", "documentos", nome_arquivo),
        os.path.join("/documentos", nome_arquivo),
        nome_arquivo
    ]
    for caminho in caminhos_possiveis:
        if os.path.exists(caminho):
            try:
                with open(caminho, "rb") as f:
                    return f.read()
            except Exception as e:
                print(f"Erro ao ler PDF em {caminho}: {e}")
    return None

def formatar_documento_para_download(texto_bruto, nome_arquivo):
    if not texto_bruto:
        return "Conteúdo indisponível para estruturação."
        
    if "calendario" in nome_arquivo.lower():
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
            r"D\s*E\s*Z\s*E\s*M\s*B\s*R\s*O": "\n\n📅 [ DEZEMBRO ] ─────────────────\n"
        }
        for regex_mes, sub_mes in meses.items():
            texto = re.sub(regex_mes, sub_mes, texto, flags=re.IGNORECASE)
        return texto.strip()

    texto_limpo = re.sub(r'\s+', ' ', texto_bruto)
    return re.sub(r'\.\s+([A-Z])', r'.\n\n\1', texto_limpo)

def gerar_conteudo_word(texto_estruturado):
    html_word = f"""
    <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
    <head><style>body {{ font-family: 'Arial', sans-serif; line-height: 1.6; padding: 20px; }} pre {{ white-space: pre-wrap; }}</style></head>
    <body><h2>DOCUMENTO OFICIAL EMITIDO PELA MINERVA AI</h2><hr/><pre>{texto_estruturado}</pre></body>
    </html>
    """
    return html_word.encode('utf-8')

# ==========================================
# 🔧 FUNÇÕES AUXILIARES DE BANCO
# ==========================================

def inicializar_banco():
    sql = """
        CREATE TABLE IF NOT EXISTS historico_minerva (
            id SERIAL PRIMARY KEY,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pergunta TEXT,
            resposta TEXT
        );
    """
    executar_query(sql, commit=True)

def salvar_no_historico(pergunta, resposta):
    sql = "INSERT INTO historico_minerva (pergunta, resposta) VALUES (%s, %s);"
    executar_query(sql, params=(pergunta, resposta), commit=True)

def limpar_historico_banco():
    try:
        executar_query("TRUNCATE TABLE historico_minerva;", commit=True)
        return True
    except:
        return False

def buscar_contexto_e_arquivo(query):
    query_lc = query.lower()
    
    mapeamento_termos = {
        "calendario": "CalendarioAcademico2026.pdf",
        "calendário": "CalendarioAcademico2026.pdf",
        "cronograma": "CalendarioAcademico2026.pdf",
        "prazos": "CalendarioAcademico2026.pdf",
        "datas": "CalendarioAcademico2026.pdf",
        "resolucao estagio": "Resolucao_Estagio.pdf",
        "resolução estágio": "Resolucao_Estagio.pdf",
        "matricula estagio": "Matricula_Estagio.pdf",
        "matrícula estágio": "Matricula_Estagio.pdf",
        "estagio": "Resolucao_Estagio.pdf",
        "estágio": "Resolucao_Estagio.pdf",
        "resolucao tcc": "Resolucao_TCC.pdf",
        "resolução tcc": "Resolucao_TCC.pdf",
        "matricula tcc": "Matricula_TCC.pdf",
        "matrícula tcc": "Matricula_TCC.pdf",
        "tcc": "Resolucao_TCC.pdf",
        "regimento fct": "Regimento_FCT.pdf",
        "regimento geral": "RegimentoGeral.pdf",
        "graduacao": "Regulamento_Graduacao.pdf",
        "graduação": "Regulamento_Graduacao.pdf"
    }
    
    nome_arquivo_alvo = None
    for chave, arq in mapeamento_termos.items():
        if chave in query_lc:
            nome_arquivo_alvo = arq
            break
            
    if nome_arquivo_alvo:
        sql = "SELECT nome_arquivo, conteudo FROM documentos_ufpa WHERE nome_arquivo = %s LIMIT 1;"
        resultados = executar_query(sql, params=(nome_arquivo_alvo,), fetch=True)
        if resultados:
            return resultados[0][0], resultados[0][1]
            
    palavras = [p for p in re.findall(r'\w+', query_lc) if len(p) > 3]
    if palavras:
        condicoes = " OR ".join(["nome_arquivo ILIKE %s" for _ in palavras])
        params = [f"%{p}%" for p in palavras]
        sql = f"SELECT nome_arquivo, conteudo FROM documentos_ufpa WHERE ({condicoes}) AND nome_arquivo NOT ILIKE '%john%' LIMIT 1;"
        resultados = executar_query(sql, params=tuple(params), fetch=True)
        if resultados:
            return resultados[0][0], resultados[0][1]
            
    return None, None

inicializar_banco()

# ─── RECONSTRUTOR DE HISTÓRICO ATIVO ──────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Olá discente! Sou a Minerva. Como posso orientá-lo hoje sobre regimentos, estágios ou calendários da FCT/UFPA?"}]
    
    sql_hist = "SELECT pergunta, resposta FROM historico_minerva ORDER BY id ASC;"
    registros_passados = executar_query(sql_hist, fetch=True)
    
    if registros_passados:
        for pergunta, resposta in registros_passados:
            st.session_state.messages.append({"role": "user", "content": pergunta})
            nome_arq, texto_raw = buscar_contexto_e_arquivo(pergunta)
            usuario_pediu_extensao = any(termo in pergunta.lower() for termo in ["extensão", "extensao", "pdf", "word", "doc", "docx", "formato"])
            
            msg_dict = {"role": "assistant", "content": resposta}
            if nome_arq:
                msg_dict["download_file"] = nome_arq
                msg_dict["exibir_extensao"] = usuario_pediu_extensao
                msg_dict["pdf_bytes"] = obter_binario_pdf(nome_arq)
                msg_dict["word_bytes"] = gerar_conteudo_word(formatar_documento_para_download(texto_raw, nome_arq))
                
            st.session_state.messages.append(msg_dict)

# ─── BARRA LATERAL ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Painel do Administrador")
    if st.button("🗑️ Limpar Conversas Atuais", use_container_width=True, type="primary"):
        if limpar_historico_banco():
            st.session_state.messages = [{"role": "assistant", "content": "Olá! Nova sessão iniciada. Como posso ajudá-lo hoje?"}]
            st.rerun()

# ─── CORPO DO CHAT ────────────────────────────────────────────────────────
st.markdown("""
    <div class="logo-container">
        <img class="logo-img" src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQm91cy9Yj1tqqsKNsqNwQGIpxjaCr0sUjCOA&s" alt="Logo UFPA">
    </div>
    <div class="chat-header">
        <h1>Minerva AI</h1>
        <p>Orientação Acadêmica Inteligente • Faculdade de Computação e Telecomunicações</p>
    </div>
""", unsafe_allow_html=True)

# Exibição do histórico na tela
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🏫" if msg["role"] == "assistant" else "👤"):
        st.markdown(f'<div class="explanation-box">{msg["content"]}</div>', unsafe_allow_html=True)
        
        if msg["role"] == "assistant" and "download_file" in msg:
            st.markdown("---")
            nome_original = msg["download_file"]
            pede_extensao = msg.get("exibir_extensao", False)
            
            if pede_extensao:
                caption_arquivo = f"📂 Arquivo Oficial Identificado: **{nome_original}**"
                label_pdf = "📥 Baixar em Formato PDF (.pdf)"
                label_word = "📝 Baixar em Formato Word (.doc)"
            else:
                nome_formatado = os.path.splitext(nome_original)[0].replace('_', ' ')
                caption_arquivo = f"📂 Documento Oficial Disponível: **{nome_formatado}**"
                label_pdf = "📥 Baixar Documento Oficial (Recomendado)"
                label_word = "📝 Baixar Versão Alternativa"

            st.caption(caption_arquivo)
            col1, col2 = st.columns(2)
            
            if msg.get("pdf_bytes"):
                col1.download_button(
                    label=label_pdf,
                    data=msg["pdf_bytes"],
                    file_name=nome_original,
                    mime="application/pdf",
                    key=f"pdf_btn_{idx}"
                )
            else:
                col1.info("⚠️ Arquivo original indisponível.")
                
            if msg.get("word_bytes"):
                col2.download_button(
                    label=label_word,
                    data=msg["word_bytes"],
                    file_name=nome_original.replace(".pdf", ".doc").replace(".PDF", ".doc"),
                    mime="application/msword",
                    key=f"word_btn_{idx}"
                )

# ─── NOVO: AÇÕES TRIVIAIS (BOTÕES DE ATALHO RÁPIDO) ───────────────────────
# Só aparecem se a conversa estiver apenas na saudação inicial
if len(st.session_state.messages) == 1:
    st.markdown("#### ✨ Sugestões de consultas frequentes:")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("📅 Calendário 2026", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Me mostre o calendario academico"})
        st.rerun()
        
    if c2.button("💼 Regras de Estágio", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Quais as resolucoes de estagio?"})
        st.rerun()
        
    if c3.button("🎓 Normativas do TCC", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Quero saber o regulamento do TCC"})
        st.rerun()

# Entrada de texto do usuário
if user_query := st.chat_input("Pergunte algo à Minerva..."):
    st.session_state.messages.append({"role": "user", "content": user_query})
    st.rerun()

# ─── PROCESSAMENTO DA RESPOSTA ────────────────────────────────────────────
if len(st.session_state.messages) > 1 and st.session_state.messages[-1]["role"] == "user":
    query_executar = st.session_state.messages[-1]["content"]
    query_lc = query_executar.lower()
    
    usuario_pediu_extensao = any(termo in query_lc for termo in ["extensão", "extensao", "pdf", "word", "doc", "docx", "formato"])
    
    with st.chat_message("assistant", avatar="🏫"):
        # Interceptação amigável para saudações curtas puras
        if query_lc.strip() in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "ajuda"]:
            resposta_final = "Olá! Como vai? Estou pronta para te ajudar a encontrar documentos da faculdade. Você pode usar os botões sugeridos acima ou digitar o documento que procura!"
            st.session_state.messages.append({"role": "assistant", "content": resposta_final})
            salvar_no_historico(query_executar, resposta_final)
            st.rerun()

        nome_arq, texto_raw = buscar_contexto_e_arquivo(query_executar)
        
        if nome_arq:
            if "calendario" in query_lc or "calendário" in query_lc or "cronograma" in query_lc:
                resposta_final = (
                    "Olá! Localizei o **Calendário Acadêmico Oficial de 2026** em nossa base de dados corporativa.\n\n"
                    "Para garantir total precisão nas datas, o documento original foi recuperado e está "
                    "pronto para visualização imediata. Efetue o download seguro abaixo:"
                )
            elif "estagio" in query_lc or "estágio" in query_lc:
                resposta_final = (
                    "Olá! Identifiquei o conjunto de normativas e resoluções voltadas aos programas de **Estágio** da FCT.\n\n"
                    "O documento lista todos os requisitos e fluxos de aprovação obrigatórios. Utilize os botões de "
                    "exportação direta abaixo:"
                )
            elif "tcc" in query_lc:
                resposta_final = (
                    "Olá! Encontrei as diretrizes unificadas do **Trabalho de Conclusão de Curso (TCC)** da faculdade.\n\n"
                    "As regras sobre prazos, bancas examinadoras e formatação podem ser consultadas diretamente "
                    "no arquivo oficial disponível abaixo:"
                )
            else:
                resposta_final = (
                    "Olá! Localizei o documento oficial solicitado diretamente no repositório institucional da FCT.\n\n"
                    "Abaixo estão as opções para você baixar o arquivo com total integridade de dados:"
                )
                
            texto_formatado = formatar_documento_para_download(texto_raw, nome_arq)
            pdf_data = obter_binario_pdf(nome_arq)
            word_data = gerar_conteudo_word(texto_formatado)
            
            nova_msg = {
                "role": "assistant",
                "content": resposta_final,
                "download_file": nome_arq,
                "exibir_extensao": usuario_pediu_extensao,
                "pdf_bytes": pdf_data,
                "word_bytes": word_data
            }
            st.session_state.messages.append(nova_msg)
            salvar_no_historico(query_executar, resposta_final)
            st.rerun()
            
        else:
            with st.status("🔍 Consultando base assistida...", expanded=False) as status:
                resposta_final = ""
                payload = [
                    {"role": "system", "content": "Você é a Minerva, assistente virtual da FCT/UFPA. Responda com clareza em português."},
                    {"role": "user", "content": query_executar}
                ]
                try:
                    response = http_session.post(
                        "http://host.docker.internal:8001/v1/chat/completions",
                        json={"messages": payload, "temperature": 0.2, "max_tokens": 300},
                        timeout=12
                    )
                    if response.status_code == 200:
                        resposta_final = response.json()["choices"][0]["message"]["content"].strip()
                        status.update(label="✨ Concluído", state="complete")
                    else:
                        resposta_final = "Não localizei registros correspondentes para esta solicitação. Tente simplificar os termos buscados."
                        status.update(label="⚠️ Aviso", state="error")
                except:
                    resposta_final = "O sistema de buscas está passando por manutenção rápida. Tente novamente em alguns segundos."
                    status.update(label="❌ Erro", state="error")
                    
            st.session_state.messages.append({"role": "assistant", "content": resposta_final})
            salvar_no_historico(query_executar, resposta_final)
            st.rerun()
