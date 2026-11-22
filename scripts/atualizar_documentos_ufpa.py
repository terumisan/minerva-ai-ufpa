import argparse
import fcntl
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request

raiz = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(raiz / "app"))
from web_segura import abrir_url, validar_url

parser = argparse.ArgumentParser(description="Atualiza os PDFs oficiais do MINERVA")
parser.add_argument("--aplicar", action="store_true")
args = parser.parse_args()

documentos = raiz / "documentos"
manifesto = raiz / "app" / "fontes_documentais.json"
fontes = json.loads(manifesto.read_text(encoding="utf-8"))
limite = 50 * 1024 * 1024

with (documentos / ".atualizacao-ufpa.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with tempfile.TemporaryDirectory(dir=documentos) as pasta:
        corpus = Path(pasta)
        alterados = []
        falhas = []
        for nome, url in sorted(fontes.items()):
            try:
                if Path(nome).name != nome or nome.startswith(".") or not nome.endswith(".pdf"):
                    raise ValueError("Nome de PDF inválido")
                validar_url(url)
                requisicao = Request(url, headers={"User-Agent": "MINERVA-AI/1.0"})
                with abrir_url(requisicao, timeout=20) as resposta:
                    dados = resposta.read(limite + 1)
                if len(dados) > limite or not dados.startswith(b"%PDF-"):
                    raise ValueError("PDF inválido ou acima de 50 MiB")
                atual = documentos / nome
                if atual.is_symlink():
                    raise ValueError("Destino é um link simbólico")
                existe = atual.is_file()
                if existe and hashlib.sha256(atual.read_bytes()).digest() == hashlib.sha256(dados).digest():
                    print(f"IGUAL {nome}", flush=True)
                    continue
                (corpus / nome).write_bytes(dados)
                alterados.append(nome)
                print(f"{'ALTERADO' if existe else 'NOVO'} {nome}", flush=True)
            except (OSError, ValueError) as erro:
                falhas.append(nome)
                print(f"FALHA {nome}: {erro}", file=sys.stderr)

        if falhas:
            sys.exit(1)
        if args.aplicar:
            for atual in documentos.glob("*.pdf"):
                if atual.name not in alterados:
                    shutil.copy2(atual, corpus / atual.name)
            subprocess.run([
                "docker", "compose", "--profile", "manutencao", "run", "--rm",
                "-v", f"{corpus}:/corpus-ufpa:ro", "ufpa_rag_ingestao",
                "--documentos", "/corpus-ufpa",
                "--fontes", "/app/fontes_documentais.json",
            ], cwd=raiz, check=True)
            for nome in alterados:
                (corpus / nome).replace(documentos / nome)
            print(f"Índice sincronizado. PDFs locais atualizados: {len(alterados)}")
