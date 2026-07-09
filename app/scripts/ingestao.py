import os
import re

import psycopg2
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastembed import TextEmbedding

# Mesmo modelo usado em minerva_hybrid.py para buscar — embeddings de
# ingestão e de pergunta precisam vir do mesmo modelo para a distância de
# cosseno fazer sentido.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
EMBEDDING_CACHE_DIR = "/app/.fastembed_cache"

# Marcadores estruturais típicos de regulamentos/resoluções da UFPA. Forçar
# uma quebra de parágrafo antes de cada um (quando ainda não há uma) dá ao
# RecursiveCharacterTextSplitter uma fronteira natural para cortar — antes,
# o texto extraído do PDF perdia toda quebra de linha ("\n" virava espaço"),
# então um artigo podia ser cortado no meio de qualquer chunk de 700
# caracteres, mesmo com overlap.
_MARCADORES_ESTRUTURAIS = re.compile(
    r"(?<!\n)\s*(?=("
    r"Art\.?\s*\d+|"
    r"CAP[ÍI]TULO\s+[IVXLCDM]+|"
    r"SE[ÇC][ÃA]O\s+[IVXLCDM]+|"
    r"T[ÍI]TULO\s+[IVXLCDM]+|"
    r"§\s*\d+"
    r"))",
    flags=re.IGNORECASE,
)


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
    # Coluna de embedding semântico (busca híbrida em minerva_hybrid.py).
    cur.execute(
        f"ALTER TABLE documentos_ufpa ADD COLUMN IF NOT EXISTS "
        f"embedding vector({EMBEDDING_DIM});"
    )
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

    # chunk_size um pouco maior que antes (900): com fronteiras estruturais
    # reais (Art./Capítulo/Seção) para o splitter preferir, cortes no meio
    # de frase ficam mais raros mesmo com chunks levemente maiores.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    modelo_embedding = TextEmbedding(
        model_name=EMBEDDING_MODEL,
        cache_dir=EMBEDDING_CACHE_DIR,
    )

    conn = conectar_banco()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE documentos_ufpa;")

    for arquivo in os.listdir(pasta_docs):
        if arquivo.endswith(".pdf"):
            caminho_completo = os.path.join(pasta_docs, arquivo)

            try:
                reader = PdfReader(caminho_completo)
                paginas = []
                for pagina in reader.pages:
                    texto_extraido = pagina.extract_text() or ""
                    # Colapsa espaços internos mas preserva a quebra de linha
                    # como fronteira de parágrafo (ao contrário da versão
                    # anterior, que substituía "\n" por " " e apagava toda
                    # estrutura do documento antes mesmo de fatiar).
                    texto_extraido = re.sub(r"[ \t]+", " ", texto_extraido)
                    paginas.append(texto_extraido.strip())

                texto_completo = "\n\n".join(p for p in paginas if p)
                texto_completo = _MARCADORES_ESTRUTURAIS.sub("\n\n", texto_completo)

                chunks = text_splitter.split_text(texto_completo)
                chunks_validos = [
                    " ".join(chunk.split())
                    for chunk in chunks
                    if len(" ".join(chunk.split())) > 20
                ]

                if not chunks_validos:
                    print(f"⚠️ {arquivo}: nenhum chunk válido extraído.")
                    continue

                embeddings = list(modelo_embedding.embed(chunks_validos))

                for texto_limpo, vetor in zip(chunks_validos, embeddings):
                    # psycopg2 não conhece o tipo "vector" nativamente — sem o
                    # pacote adaptador pgvector, formata como texto "[v1,v2,...]"
                    # e deixa o Postgres fazer o cast (::vector).
                    vetor_literal = "[" + ",".join(f"{v:.6f}" for v in vetor.tolist()) + "]"
                    cur.execute(
                        "INSERT INTO documentos_ufpa (nome_arquivo, conteudo, embedding) "
                        "VALUES (%s, %s, %s::vector);",
                        (arquivo, texto_limpo, vetor_literal),
                    )
                print(f"✔️ {arquivo} indexado com sucesso! ({len(chunks_validos)} chunks)")
            except Exception as e:
                print(f"⚠️ Erro ao processar {arquivo}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("🚀 [SUCESSO] Base de dados limpa e reindexada!")


if __name__ == "__main__":
    criar_tabela()
    extrair_e_salvar_texto()
