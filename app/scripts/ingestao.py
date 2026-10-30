import os
import re
import argparse
import hashlib
import json
import math
from collections import defaultdict, deque
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import closing

import psycopg2
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastembed import TextEmbedding

# Mesmo modelo usado em minerva_hybrid.py para buscar — embeddings de
# ingestão e de pergunta precisam vir do mesmo modelo para a distância de
# cosseno fazer sentido.
#
# mpnet-base-v2 substituiu o MiniLM-L12 (medido com comparar_embeddings.py
# contra as 720 perguntas de app/tests/data/eval_minerva_qa.json, comparando
# só a busca semântica): hit@1 18,3%->30,8%, hit@3 32,9%->47,4%,
# hit@6 44,2%->57,4%. O multilingual-e5-large media ainda melhor
# (hit@6 66,1%) mas é 2,3GB (vs 1GB do mpnet) — descartado pelo risco de
# memória nesta máquina (12-14GB RAM, já teve um incidente de swap com o
# container do LLM).
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIM = 768
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
        host=os.getenv("DB_HOST", "ufpa_rag_db"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "ufpa_rag"),
        user=os.getenv("DB_USER", "admin"),
        # Sem default: credencial real deve vir do .env (ver .env.example),
        # consumido pelo docker-compose.yml como env var do container.
        password=os.environ["DB_PASSWORD"],
    )


PROCESSAMENTO = "estrutura-900-150-v2"
LOCK_ID = 73614208


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def configuracao():
    return json.dumps({
        "modelo": EMBEDDING_MODEL, "dimensao": EMBEDDING_DIM,
        "fastembed": version("fastembed"), "pypdf": version("pypdf"),
        "splitter": version("langchain-text-splitters"),
        "processamento": PROCESSAMENTO,
    }, sort_keys=True)


def criar_tabela():
    """Migração aditiva: nunca remove coluna, embedding ou corpus ativo."""
    with closing(conectar_banco()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute("""CREATE TABLE IF NOT EXISTS documentos_ufpa (
                id SERIAL PRIMARY KEY, nome_arquivo TEXT, conteudo TEXT,
                embedding vector(768))""")
            cur.execute("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'documentos_ufpa'::regclass AND attname = 'embedding' AND NOT attisdropped")
            tipo = cur.fetchone()
            if tipo and tipo[0] != f"vector({EMBEDDING_DIM})":
                raise ValueError("Dimensão incompatível; criar outro índice antes de migrar")
            cur.execute("ALTER TABLE documentos_ufpa ADD COLUMN IF NOT EXISTS embedding vector(768)")
            for coluna, tipo in (
                ("chunk_uid", "TEXT"), ("chunk_sha256", "TEXT"),
                ("documento_sha256", "TEXT"), ("pagina_inicio", "INTEGER"),
                ("pagina_fim", "INTEGER"), ("source_url", "TEXT"),
                ("embedding_config", "TEXT"),
            ):
                cur.execute(f"ALTER TABLE documentos_ufpa ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_uid ON documentos_ufpa (chunk_uid)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conteudo_trgm ON documentos_ufpa USING gin (conteudo gin_trgm_ops)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conteudo_tsv ON documentos_ufpa USING gin (to_tsvector('portuguese', conteudo))")
            cur.execute("""CREATE TABLE IF NOT EXISTS minerva_documentos_manifesto (
                nome_arquivo TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                embedding_config TEXT NOT NULL, source_url TEXT,
                chunks INTEGER NOT NULL, atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now())""")


def extrair_chunks(caminho):
    """Páginas físicas (1-based), incluindo trechos que atravessam páginas."""
    reader = PdfReader(caminho)
    paginas, intervalos, pos = [], [], 0
    for numero, pagina in enumerate(reader.pages, 1):
        texto = re.sub(r"[ \t]+", " ", pagina.extract_text() or "").strip()
        if not texto:
            continue
        texto = _MARCADORES_ESTRUTURAIS.sub("\n\n", texto)
        if paginas:
            pos += 2
        intervalos.append((pos, pos + len(texto), numero))
        paginas.append(texto)
        pos += len(texto)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=150, add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    ocorrencias = defaultdict(int)
    for doc in splitter.create_documents(["\n\n".join(paginas)]):
        texto = " ".join(doc.page_content.split())
        if len(texto) <= 20:
            continue
        inicio = doc.metadata["start_index"]
        fim = inicio + len(doc.page_content)
        nums = [n for a, b, n in intervalos if a < fim and b > inicio]
        if inicio < 0 or not nums:
            raise ValueError("Não foi possível localizar a página do trecho")
        digest = sha256(texto.encode())
        ocorrencias[digest] += 1
        uid = sha256(f"{caminho.name}\0{digest}\0{ocorrencias[digest]}".encode())
        chunks.append((texto, uid, digest, min(nums), max(nums)))
    if not chunks:
        raise ValueError(f"PDF sem texto extraível: {caminho.name}")
    return chunks


def carregar_fontes(caminho):
    if caminho is None:
        return {}
    fontes = json.loads(Path(caminho).read_text())
    if not isinstance(fontes, dict):
        raise ValueError("Fontes devem mapear nome do PDF para URL oficial")
    for nome, url in fontes.items():
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (Path(nome).name != nome or parsed.scheme != "https"
                or not (host == "ufpa.br" or host.endswith(".ufpa.br"))
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError(f"Fonte inválida: {nome}")
    return fontes


def atualizar_corpus(conn, pasta, modelo_factory=None, batch_size=8, fontes=None, force=False):
    """Prepara tudo em staging temporário e publica em uma única transação.

    Uma falha em qualquer PDF/vetor/SQL reverte a execução inteira. Arquivos
    ausentes da pasta não são excluídos da base automaticamente.
    """
    if not 1 <= batch_size <= 8:
        raise ValueError("batch_size deve estar entre 1 e 8")
    arquivos = sorted(Path(pasta).glob("*.pdf"))
    if not arquivos:
        raise ValueError("Nenhum PDF encontrado; base preservada")
    fontes = fontes or {}
    config = configuracao()
    modelo = None
    alterados, ignorados, metadados = [], [], []
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (LOCK_ID,))
            if not cur.fetchone()[0]:
                raise RuntimeError("Outra ingestão está em andamento")
            cur.execute("SELECT DISTINCT embedding_config FROM documentos_ufpa WHERE embedding_config IS NOT NULL AND nome_arquivo <> ALL(%s)", ([a.name for a in arquivos],))
            if any(r[0] != config for r in cur.fetchall()):
                raise ValueError("Há documentos ausentes com outra configuração de embedding; migrar o corpus completo")
            cur.execute("""CREATE TEMP TABLE ingestao_staging (
                nome_arquivo TEXT, conteudo TEXT, embedding vector(768),
                chunk_uid TEXT, chunk_sha256 TEXT, documento_sha256 TEXT,
                pagina_inicio INTEGER, pagina_fim INTEGER, source_url TEXT,
                embedding_config TEXT) ON COMMIT DROP""")
            for arquivo in arquivos:
                digest = sha256(arquivo.read_bytes())
                cur.execute("SELECT sha256, embedding_config, source_url, chunks FROM minerva_documentos_manifesto WHERE nome_arquivo = %s", (arquivo.name,))
                anterior = cur.fetchone()
                fonte = fontes.get(arquivo.name, anterior[2] if anterior else None)
                cur.execute("SELECT count(*), count(*) FILTER (WHERE embedding IS NOT NULL AND chunk_uid IS NOT NULL AND documento_sha256 = %s AND embedding_config = %s) FROM documentos_ufpa WHERE nome_arquivo = %s", (digest, config, arquivo.name))
                total, count = cur.fetchone()
                if not force and anterior and anterior[:2] == (digest, config) and total == count == anterior[3] and count > 0:
                    if anterior[2] != fonte:
                        metadados.append((fonte, arquivo.name, digest))
                    else:
                        ignorados.append(arquivo.name)
                    continue
                chunks = extrair_chunks(arquivo)
                if modelo is None:
                    modelo = (modelo_factory or (lambda: TextEmbedding(
                        model_name=EMBEDDING_MODEL, cache_dir=EMBEDDING_CACHE_DIR,
                        threads=2,
                    )))()
                # Lotes explícitos também limitam o texto entregue ao modelo.
                for i in range(0, len(chunks), batch_size):
                    lote = chunks[i:i + batch_size]
                    vetores = list(modelo.passage_embed([c[0] for c in lote], batch_size=batch_size))
                    if len(vetores) != len(lote):
                        raise ValueError("Quantidade incorreta de embeddings")
                    for chunk, vetor in zip(lote, vetores, strict=True):
                        valores = list(vetor)
                        if len(valores) != EMBEDDING_DIM or not all(math.isfinite(float(v)) for v in valores) or not any(valores):
                            raise ValueError("Embedding inválido; base preservada")
                        literal = "[" + ",".join(f"{v:.6f}" for v in valores) + "]"
                        texto, uid, chunk_hash, inicio, fim = chunk
                        cur.execute("INSERT INTO ingestao_staging VALUES (%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s)", (arquivo.name, texto, literal, uid, chunk_hash, digest, inicio, fim, fonte, config))
                # Detecta alteração do PDF durante o processamento.
                if sha256(arquivo.read_bytes()) != digest:
                    raise ValueError("PDF mudou durante a ingestão")
                alterados.append((arquivo.name, digest, fonte, len(chunks)))
                print(f"Preparado: {arquivo.name} ({len(chunks)} trechos)", flush=True)

            # Somente agora toca nas linhas ativas, com IDs preservados para
            # conteúdo idêntico, inclusive na primeira migração do legado.
            for fonte, nome, digest in metadados:
                cur.execute("UPDATE documentos_ufpa SET source_url=%s WHERE nome_arquivo=%s AND documento_sha256=%s", (fonte,nome,digest))
                cur.execute("UPDATE minerva_documentos_manifesto SET source_url=%s, atualizado_em=now() WHERE nome_arquivo=%s AND sha256=%s", (fonte,nome,digest))
            for nome, digest, fonte, total in alterados:
                cur.execute("SELECT id, conteudo FROM documentos_ufpa WHERE nome_arquivo = %s ORDER BY id", (nome,))
                existentes = defaultdict(deque)
                for chave, texto in cur.fetchall():
                    existentes[texto].append(chave)
                cur.execute("SELECT conteudo, embedding::text, chunk_uid, chunk_sha256, documento_sha256, pagina_inicio, pagina_fim, source_url, embedding_config FROM ingestao_staging WHERE nome_arquivo = %s ORDER BY ctid", (nome,))
                for row in cur.fetchall():
                    if existentes[row[0]]:
                        chave = existentes[row[0]].popleft()
                        cur.execute("UPDATE documentos_ufpa SET conteudo=%s, embedding=%s::vector, chunk_uid=%s, chunk_sha256=%s, documento_sha256=%s, pagina_inicio=%s, pagina_fim=%s, source_url=%s, embedding_config=%s WHERE id=%s", (*row, chave))
                    else:
                        cur.execute("INSERT INTO documentos_ufpa (conteudo, embedding, chunk_uid, chunk_sha256, documento_sha256, pagina_inicio, pagina_fim, source_url, embedding_config, nome_arquivo) VALUES (%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s)", (*row, nome))
                sobras = [chave for fila in existentes.values() for chave in fila]
                if sobras:
                    cur.execute("DELETE FROM documentos_ufpa WHERE id = ANY(%s)", (sobras,))
                cur.execute("""INSERT INTO minerva_documentos_manifesto (nome_arquivo,sha256,embedding_config,source_url,chunks)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT (nome_arquivo) DO UPDATE SET
                    sha256=EXCLUDED.sha256, embedding_config=EXCLUDED.embedding_config,
                    source_url=EXCLUDED.source_url, chunks=EXCLUDED.chunks, atualizado_em=now()""", (nome,digest,config,fonte,total))
    resumo = {"atualizados": len(alterados), "inalterados": len(ignorados)}
    if metadados:
        resumo["metadados_atualizados"] = len(metadados)
    return resumo


def extrair_e_salvar_texto(pasta="/documentos", batch_size=8, fontes=None, force=False):
    conn = conectar_banco()
    try:
        return atualizar_corpus(conn, pasta, batch_size=batch_size, fontes=fontes, force=force)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Ingestão incremental e atômica de PDFs")
    parser.add_argument("--documentos", default="/documentos")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--fontes", help="JSON de nome do PDF para URL oficial")
    parser.add_argument("--force", action="store_true", help="Reprocessar também PDFs inalterados")
    args = parser.parse_args()
    fontes = carregar_fontes(args.fontes)
    criar_tabela()
    print(extrair_e_salvar_texto(args.documentos, args.batch_size, fontes, args.force))


if __name__ == "__main__":
    main()
