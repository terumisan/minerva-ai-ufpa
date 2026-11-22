"""Valida PDFs e publica o catálogo de perguntas/contextos no PostgreSQL."""
import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from minerva_qa_catalogo import validar_dataset, validar_pdfs, sincronizar_catalogo  # noqa: E402
from scripts.ingestao import conectar_banco  # noqa: E402


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[1]/"minerva_dataset.json")
    p.add_argument("--documentos", type=Path, default=Path("/documentos"))
    args=p.parse_args()
    dados=json.loads(args.dataset.read_text())
    entradas=validar_dataset(dados)
    validar_pdfs(entradas,args.documentos)
    with closing(conectar_banco()) as conn:
        print(json.dumps(sincronizar_catalogo(conn,dados),ensure_ascii=False))


if __name__ == "__main__":
    main()
