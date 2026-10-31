"""Testa, para cada par pergunta/resposta do dataset de avaliação (ver
gerar_eval_dataset.py), se a busca híbrida (minerva_hybrid.buscar_em_documentos_postgres
— a mesma função usada em produção) recupera o chunk de origem entre os
top-N resultados. Rápido (sem tocar o LLM): mede só a qualidade do
retrieval, que é a causa mais comum de resposta ruim.

Roda sobre TODAS as perguntas geradas (diferente de testar_e2e_amostra.py,
que usa uma amostra menor e chama o LLM de verdade).
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestao import conectar_banco  # noqa: E402
from minerva_hybrid import buscar_em_documentos_postgres  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
OUT_PATH = DATA_DIR / "resultado_retrieval.jsonl"


def _carregar_perguntas() -> list[dict]:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))["perguntas"]


def main() -> None:
    perguntas = _carregar_perguntas()
    conn = conectar_banco()

    resultados = []
    por_arquivo = defaultdict(lambda: {"total": 0, "encontrados": 0})

    inicio = time.time()
    for i, item in enumerate(perguntas, start=1):
        fontes = buscar_em_documentos_postgres(conn, item["pergunta"], limite=6)

        posicao = None
        for idx, f in enumerate(fontes, start=1):
            if f["titulo"] == item["arquivo_fonte"] and f["trecho"] == item["trecho_fonte"]:
                posicao = idx
                break

        registro = {
            "chunk_id": item["chunk_id"],
            "arquivo_fonte": item["arquivo_fonte"],
            "pergunta": item["pergunta"],
            "encontrado": posicao is not None,
            "posicao": posicao,
        }
        resultados.append(registro)

        por_arquivo[item["arquivo_fonte"]]["total"] += 1
        if posicao is not None:
            por_arquivo[item["arquivo_fonte"]]["encontrados"] += 1

        if i % 25 == 0:
            decorrido = time.time() - inicio
            print(f"[{i}/{len(perguntas)}] {decorrido:.0f}s decorridos")

    conn.close()

    OUT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resultados) + "\n",
        encoding="utf-8",
    )

    total = len(resultados)
    encontrados = sum(1 for r in resultados if r["encontrado"])
    top1 = sum(1 for r in resultados if r["posicao"] == 1)
    top3 = sum(1 for r in resultados if r["posicao"] is not None and r["posicao"] <= 3)

    print(f"\n=== Resumo geral ({total} perguntas) ===")
    print(f"hit-rate@6: {encontrados}/{total} ({100*encontrados/total:.1f}%)")
    print(f"hit-rate@3: {top3}/{total} ({100*top3/total:.1f}%)")
    print(f"hit-rate@1: {top1}/{total} ({100*top1/total:.1f}%)")

    print("\n=== Por documento ===")
    for arquivo, dados in sorted(por_arquivo.items(), key=lambda kv: -kv[1]["total"]):
        taxa = 100 * dados["encontrados"] / dados["total"] if dados["total"] else 0
        print(f"{arquivo}: {dados['encontrados']}/{dados['total']} ({taxa:.1f}%)")


if __name__ == "__main__":
    main()
