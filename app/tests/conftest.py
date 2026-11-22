import os
import uuid
from contextlib import closing

import psycopg2
import pytest
from scripts import ingestao as ing


@pytest.fixture
def banco(monkeypatch):
    dsn = os.getenv("MINERVA_TEST_DSN")
    if not dsn:
        pytest.skip("Defina MINERVA_TEST_DSN para integração com PostgreSQL/pgvector")
    schema = "teste_" + uuid.uuid4().hex
    with closing(psycopg2.connect(dsn)) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute(f"CREATE SCHEMA {schema}")
        def conectar():
            return psycopg2.connect(dsn, options=f"-c search_path={schema},public")
        monkeypatch.setattr(ing, "conectar_banco", conectar)
        try:
            ing.criar_tabela()
            with closing(conectar()) as conn:
                yield conn
        finally:
            with admin.cursor() as cur:
                cur.execute(f"DROP SCHEMA {schema} CASCADE")



@pytest.fixture
def pdfs(tmp_path, monkeypatch):
    def extrair(p):
        texto = p.read_text()
        if texto == "corrompido":
            raise ValueError("PDF corrompido")
        return [(texto, ing.sha256((p.name + texto).encode()), ing.sha256(texto.encode()), 1, 2)]
    monkeypatch.setattr(ing, "extrair_chunks", extrair)
    (tmp_path / "a.pdf").write_text("Texto institucional de teste")
    return tmp_path

