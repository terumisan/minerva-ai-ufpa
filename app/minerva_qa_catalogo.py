"""Catálogo de perguntas: contexto e relações não autorizam respostas literais."""
import hashlib
import json
import re
from pathlib import Path

from psycopg2.extras import Json
from pypdf import PdfReader

from minerva_dataset import _norm


def validar_dataset(dados):
    entradas = dados["respostas_especificas"]
    por_id = {e["id"]: e for e in entradas}
    if len(por_id) != len(entradas):
        raise ValueError("IDs de perguntas duplicados")
    aliases = {}
    for e in entradas:
        if not e.get("pergunta"):
            raise ValueError("Pergunta vazia")
        for texto in [e["pergunta"], *e.get("variacoes", [])]:
            normalizado = _norm(texto)
            if not normalizado:
                raise ValueError("Variação vazia")
            if e.get("ativo", True):
                outro = aliases.setdefault(normalizado, e["id"])
                if outro != e["id"]:
                    raise ValueError(f"Variação ambígua entre {outro} e {e['id']}")
        for r in e.get("relacoes", []):
            if r["id"] not in por_id or r["id"] == e["id"]:
                raise ValueError("Relação sem destino válido")
        c = e.get("contexto_documental")
        if not c:
            continue
        if (c["documento"] != e["fonte_documento"]
                or not re.fullmatch(r"[a-f0-9]{64}", c["documento_sha256"])
                or not c.get("escopo") or not c.get("dispositivo")):
            raise ValueError("Contexto documental inválido")
        paginas = c["paginas_fisicas"]
        if not paginas or any(type(p) is not int or p < 1 for p in paginas):
            raise ValueError("Páginas inválidas")
        if set(paginas) != {v["pagina_fisica"] for v in c["evidencias"]}:
            raise ValueError("Página sem evidência")
        for v in c["evidencias"]:
            if hashlib.sha256(v["texto"].encode()).hexdigest() != v["texto_sha256"]:
                raise ValueError("Hash do texto da evidência diverge")
    return entradas


def validar_pdfs(entradas, pasta):
    cache = {}
    for e in entradas:
        c = e.get("contexto_documental")
        if not c:
            continue
        nome = c["documento"]
        if Path(nome).name != nome:
            raise ValueError("Nome de documento inválido")
        if nome not in cache:
            path = Path(pasta) / nome
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            paginas = [" ".join((p.extract_text() or "").split()) for p in PdfReader(path).pages]
            cache[nome] = digest, paginas
        digest, paginas = cache[nome]
        if digest != c["documento_sha256"]:
            raise ValueError(f"PDF alterado: {nome}")
        for v in c["evidencias"]:
            n = v["pagina_fisica"]
            if n > len(paginas) or paginas[n-1] != v["texto"]:
                raise ValueError(f"Página não corresponde ao PDF: {nome}, {n}")


def sincronizar_catalogo(conn, dados):
    entradas = validar_dataset(dados)
    serializado = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(serializado.encode()).hexdigest()
    with conn, conn.cursor() as cur:
        # Compartilha o lock do corpus: não publica vínculos durante ingestão.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (73614208,))
        cur.execute("""CREATE TABLE IF NOT EXISTS minerva_qa_versoes (
            sha256 TEXT PRIMARY KEY, versao TEXT NOT NULL,
            dataset JSONB NOT NULL, registrado_em TIMESTAMPTZ DEFAULT now())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS minerva_perguntas_respostas (
            id TEXT PRIMARY KEY, pergunta TEXT NOT NULL, resposta TEXT,
            ativo BOOLEAN NOT NULL, entrada JSONB NOT NULL,
            dataset_sha256 TEXT NOT NULL REFERENCES minerva_qa_versoes(sha256),
            atualizado_em TIMESTAMPTZ DEFAULT now())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS minerva_qa_variacoes (
            entrada_id TEXT REFERENCES minerva_perguntas_respostas(id) ON DELETE CASCADE,
            texto TEXT NOT NULL, normalizada TEXT NOT NULL, tipo TEXT NOT NULL,
            PRIMARY KEY (entrada_id,normalizada))""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qa_normalizada ON minerva_qa_variacoes(normalizada)")
        cur.execute("""CREATE TABLE IF NOT EXISTS minerva_qa_relacoes (
            origem_id TEXT REFERENCES minerva_perguntas_respostas(id) ON DELETE CASCADE,
            destino_id TEXT REFERENCES minerva_perguntas_respostas(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL, motivo TEXT NOT NULL,
            PRIMARY KEY (origem_id,destino_id,tipo), CHECK (origem_id <> destino_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS minerva_qa_evidencias (
            entrada_id TEXT REFERENCES minerva_perguntas_respostas(id) ON DELETE CASCADE,
            chunk_uid TEXT REFERENCES documentos_ufpa(chunk_uid) ON DELETE CASCADE,
            documento_sha256 TEXT NOT NULL, pagina INTEGER NOT NULL,
            papel TEXT NOT NULL DEFAULT 'contexto_de_pagina',
            PRIMARY KEY (entrada_id,chunk_uid,pagina))""")
        cur.execute("INSERT INTO minerva_qa_versoes (sha256,versao,dataset) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (digest,dados["versao_dataset"],Json(dados)))
        for e in entradas:
            cur.execute("""INSERT INTO minerva_perguntas_respostas (id,pergunta,resposta,ativo,entrada,dataset_sha256)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET pergunta=EXCLUDED.pergunta,
                resposta=EXCLUDED.resposta, ativo=EXCLUDED.ativo, entrada=EXCLUDED.entrada,
                dataset_sha256=EXCLUDED.dataset_sha256, atualizado_em=now()
                WHERE minerva_perguntas_respostas.entrada IS DISTINCT FROM EXCLUDED.entrada""",
                (e["id"],e["pergunta"],e.get("resposta_literal"),e.get("ativo",True),Json(e),digest))
        cur.execute("UPDATE minerva_perguntas_respostas SET ativo=FALSE WHERE NOT (id=ANY(%s))", ([e["id"] for e in entradas],))
        for e in entradas:
            for tabela in ("minerva_qa_variacoes", "minerva_qa_evidencias"):
                cur.execute(f"DELETE FROM {tabela} WHERE entrada_id=%s", (e["id"],))
            cur.execute("DELETE FROM minerva_qa_relacoes WHERE origem_id=%s", (e["id"],))
            for tipo,textos in (("principal",[e["pergunta"]]),("variacao",e.get("variacoes",[]))):
                for texto in textos:
                    cur.execute("INSERT INTO minerva_qa_variacoes VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (e["id"],texto,_norm(texto),tipo))
            for r in e.get("relacoes",[]):
                cur.execute("INSERT INTO minerva_qa_relacoes VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (e["id"],r["id"],r["tipo"],r["motivo"]))
            c = e.get("contexto_documental")
            if not c:
                continue
            cur.execute("SELECT sha256 FROM minerva_documentos_manifesto WHERE nome_arquivo=%s", (c["documento"],))
            versao = cur.fetchone()
            if not versao or versao[0] != c["documento_sha256"]:
                raise ValueError(f"Versão do corpus diverge: {e['id']}")
            for p in c["paginas_fisicas"]:
                cur.execute("SELECT chunk_uid FROM documentos_ufpa WHERE nome_arquivo=%s AND documento_sha256=%s AND pagina_inicio<=%s AND pagina_fim>=%s AND chunk_uid IS NOT NULL", (c["documento"],c["documento_sha256"],p,p))
                trechos = cur.fetchall()
                if not trechos:
                    raise ValueError(f"Página sem trechos no corpus: {e['id']}, página {p}")
                for (uid,) in trechos:
                    cur.execute("INSERT INTO minerva_qa_evidencias (entrada_id,chunk_uid,documento_sha256,pagina) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (e["id"],uid,c["documento_sha256"],p))
        resumo = {"dataset_sha256":digest}
        for tabela in ("minerva_perguntas_respostas","minerva_qa_variacoes","minerva_qa_relacoes","minerva_qa_evidencias"):
            cur.execute(f"SELECT count(*) FROM {tabela}")
            resumo[tabela] = cur.fetchone()[0]
    return resumo
