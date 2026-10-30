import os
import uuid
from contextlib import closing
from pathlib import Path

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


class Modelo:
    def passage_embed(self, textos, batch_size):
        assert batch_size <= 8 and len(textos) <= batch_size
        return [[0.1] * 768 for _ in textos]


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


def linhas(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome_arquivo, conteudo, embedding::text, chunk_uid, documento_sha256 FROM documentos_ufpa ORDER BY id")
        return cur.fetchall()


def test_incremental_ids_estaveis_e_sem_revetorizar(banco, pdfs):
    assert ing.atualizar_corpus(banco, pdfs, Modelo)["atualizados"] == 1
    antes = linhas(banco)
    def proibido():
        pytest.fail("Não deve carregar o modelo se os arquivos não mudaram")
    assert ing.atualizar_corpus(banco, pdfs, proibido) == {"atualizados": 0, "inalterados": 1}
    assert linhas(banco) == antes
    # Bytes/versão do arquivo mudam, mas o texto extraído é idêntico.
    (pdfs / "a.pdf").write_text("Outra representação do PDF")
    original = antes[0][2]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ing, "extrair_chunks", lambda p: [(original, antes[0][4], ing.sha256(original.encode()), 1, 2)])
        ing.atualizar_corpus(banco, pdfs, Modelo)
    assert linhas(banco)[0][0] == antes[0][0]


def test_falha_em_segundo_pdf_preserva_corpus_e_manifesto(banco, pdfs):
    ing.atualizar_corpus(banco, pdfs, Modelo)
    antes = linhas(banco)
    (pdfs / "a.pdf").write_text("Texto atualizado")
    (pdfs / "z.pdf").write_text("corrompido")
    with pytest.raises(ValueError, match="corrompido"):
        ing.atualizar_corpus(banco, pdfs, Modelo)
    assert linhas(banco) == antes
    (pdfs / "z.pdf").unlink()
    assert ing.atualizar_corpus(banco, pdfs, Modelo)["atualizados"] == 1


def test_vetor_invalido_reverte_tudo(banco, pdfs):
    ing.atualizar_corpus(banco, pdfs, Modelo)
    antes = linhas(banco)
    (pdfs / "a.pdf").write_text("Texto atualizado")
    class Ruim:
        def passage_embed(self, textos, batch_size):
            return [[float("nan")] * 768 for _ in textos]
    with pytest.raises(ValueError, match="Embedding inválido"):
        ing.atualizar_corpus(banco, pdfs, Ruim)
    assert linhas(banco) == antes


def test_arquivo_ausente_nao_apaga_base_e_lote_invalido_recusado(banco, pdfs):
    ing.atualizar_corpus(banco, pdfs, Modelo)
    antes = linhas(banco)
    (pdfs / "a.pdf").unlink()
    with pytest.raises(ValueError, match="Nenhum PDF"):
        ing.atualizar_corpus(banco, pdfs, Modelo)
    assert linhas(banco) == antes
    with pytest.raises(ValueError, match="batch_size"):
        ing.atualizar_corpus(banco, pdfs, Modelo, batch_size=256)


def test_dimensao_incompativel_nao_remove_embeddings(banco):
    with banco, banco.cursor() as cur:
        cur.execute("ALTER TABLE documentos_ufpa ALTER COLUMN embedding TYPE vector(3)")
        cur.execute("INSERT INTO documentos_ufpa (conteudo,embedding) VALUES ('preservado','[1,2,3]')")
    with pytest.raises(ValueError, match="Dimensão incompatível"):
        ing.criar_tabela()
    assert linhas(banco)[0][3] == "[1,2,3]"


def test_legado_preserva_id_de_texto_identico(banco, pdfs):
    with banco, banco.cursor() as cur:
        cur.execute("INSERT INTO documentos_ufpa (nome_arquivo,conteudo) VALUES ('a.pdf',%s) RETURNING id", ((pdfs / "a.pdf").read_text(),))
        chave = cur.fetchone()[0]
    ing.atualizar_corpus(banco, pdfs, Modelo)
    atual = linhas(banco)
    assert len(atual) == 1 and atual[0][0] == chave and atual[0][4]


def test_extracao_paginas_repeticao_e_hash_estavel(monkeypatch):
    class Pagina:
        def extract_text(self):
            return "Texto do manual institucional. " * 8
    class Reader:
        pages = [Pagina(), Pagina()]
    monkeypatch.setattr(ing, "PdfReader", lambda p: Reader())
    a = ing.extrair_chunks(Path("manual.pdf"))
    assert a == ing.extrair_chunks(Path("manual.pdf"))
    assert a[0][3:] == (1, 2)


def test_fontes_rejeitam_host_semelhante(tmp_path):
    p = tmp_path / "fontes.json"
    p.write_text('{"manual.pdf":"https://ufpa.br.exemplo.com/manual.pdf"}')
    with pytest.raises(ValueError):
        ing.carregar_fontes(p)


def test_historico_isola_leitura_lista_edicao_exclusao_e_feedback(banco, monkeypatch):
    import db
    from types import SimpleNamespace
    monkeypatch.setattr(db, "db_pool", SimpleNamespace(getconn=lambda: banco, putconn=lambda c: None))
    estado = SimpleNamespace(session_id="usuario_a")
    monkeypatch.setattr(db.st, "session_state", estado)
    db.inicializar_banco()
    chave = db.salvar_no_historico("conversa_a", "Pergunta privada", "Resposta privada")
    assert chave
    estado.session_id = "usuario_b"
    assert db.carregar_historico_conversa("conversa_a") == []
    assert db.listar_conversas_dispositivo() == []
    db.registrar_feedback(chave, "negativo")
    db.renomear_conversa("conversa_a", "Invadida")
    db.excluir_conversa("conversa_a")
    estado.session_id = "usuario_a"
    assert db.carregar_historico_conversa("conversa_a") == [(chave, "Pergunta privada", "Resposta privada", None)]
    assert db.listar_conversas_dispositivo()[0][1] == "Pergunta privada"
    db.registrar_feedback(chave, "positivo")
    assert db.carregar_historico_conversa("conversa_a")[0][3] == "positivo"


def test_falha_na_publicacao_sql_reverte_primeiro_documento(banco, pdfs):
    ing.atualizar_corpus(banco, pdfs, Modelo)
    antes = linhas(banco)
    with banco, banco.cursor() as cur:
        cur.execute("ALTER TABLE documentos_ufpa ADD CONSTRAINT falha_teste CHECK (nome_arquivo <> 'z.pdf')")
    (pdfs / "a.pdf").write_text("Primeiro documento alterado")
    (pdfs / "z.pdf").write_text("Segundo documento válido mas rejeitado pelo banco")
    with pytest.raises(psycopg2.errors.CheckViolation):
        ing.atualizar_corpus(banco, pdfs, Modelo)
    assert linhas(banco) == antes


def test_ingestoes_concorrentes_nao_se_sobrepoem(banco, pdfs):
    with closing(ing.conectar_banco()) as outra, outra, outra.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ing.LOCK_ID,))
        with pytest.raises(RuntimeError, match="Outra ingestão"):
            ing.atualizar_corpus(banco, pdfs, Modelo)
    assert ing.atualizar_corpus(banco, pdfs, Modelo)["atualizados"] == 1


def test_retencao_simula_sem_apagar_e_so_aplica_com_flag(banco):
    from scripts.retencao_historico import expirar
    with banco, banco.cursor() as cur:
        cur.execute("CREATE TABLE historico_minerva (data_hora TIMESTAMP)")
        cur.execute("INSERT INTO historico_minerva VALUES (now() - interval '60 days'), (now())")
    assert expirar(banco, 30)["registros"]["historico_minerva"] == 1
    with banco.cursor() as cur:
        cur.execute("SELECT count(*) FROM historico_minerva")
        assert cur.fetchone()[0] == 2
    assert expirar(banco, 30, aplicar=True)["aplicado"]
    with banco.cursor() as cur:
        cur.execute("SELECT count(*) FROM historico_minerva")
        assert cur.fetchone()[0] == 1
