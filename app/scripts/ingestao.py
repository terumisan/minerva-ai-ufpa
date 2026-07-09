import os
import psycopg2
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def conectar_banco():
    return psycopg2.connect(
        host="ufpa_rag_db",
        database="ufpa_rag",
        user="admin",
        password="ufpa_senha_123"
    )

def criar_tabela():
    conn = conectar_banco()
    cur = conn.cursor()
    # Ativa extensões necessárias
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;") # Ajuda na indexação textual complementar
    
    # Cria a tabela evoluída com índice de texto completo
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documentos_ufpa (
            id SERIAL PRIMARY KEY,
            nome_arquivo TEXT,
            conteudo TEXT
        );
    """)
    # Cria um índice de busca avançada para acelerar e dar inteligência ao Postgres
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conteudo_trgm ON documentos_ufpa USING gin (conteudo gin_trgm_ops);")
    # Índice para a busca full-text (to_tsvector/to_tsquery) usada por
    # minerva_hybrid.buscar_em_documentos_postgres — sem ele, o Postgres
    # recalcula to_tsvector(conteudo) linha a linha a cada pergunta.
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_conteudo_tsv ON documentos_ufpa "
        "USING gin (to_tsvector('portuguese', conteudo));"
    )
    conn.commit()
    cur.close()
    conn.close()
    print("🤖 [BANCO] Nova estrutura de tabela otimizada criada!")

def extrair_e_salvar_texto():
    pasta_docs = "/documentos"
    if not os.path.exists(pasta_docs) or not os.listdir(pasta_docs):
        print("❌ [ERRO] Nenhum PDF encontrado.")
        return

    # Otimização do fatiador: chunks ligeiramente menores para focar na resposta exata
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)

    conn = conectar_banco()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE documentos_ufpa;") 

    for arquivo in os.listdir(pasta_docs):
        if arquivo.endswith(".pdf"):
            caminho_completo = os.path.join(pasta_docs, arquivo)
            
            try:
                reader = PdfReader(caminho_completo)
                texto_completo = ""
                for pagina in reader.pages:
                    # Limpeza básica de quebras de linha órfãs que quebram o entendimento da IA
                    texto_extraido = pagina.extract_text() or ""
                    texto_completo += " " + texto_extraido.replace("\n", " ")
                
                chunks = text_splitter.split_text(texto_completo)
                
                for chunk in chunks:
                    texto_limpo = " ".join(chunk.split()) # Remove espaços duplos
                    if len(texto_limpo) > 20: # Ignora pedaços insignificantes
                        cur.execute(
                            "INSERT INTO documentos_ufpa (nome_arquivo, conteudo) VALUES (%s, %s);",
                            (arquivo, texto_limpo)
                        )
                print(f"✔️ {arquivo} indexado com sucesso!")
            except Exception as e:
                print(f"⚠️ Erro ao processar {arquivo}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("🚀 [SUCESSO] Base de dados limpa e reindexada!")

if __name__ == "__main__":
    criar_tabela()
    extrair_e_salvar_texto()
