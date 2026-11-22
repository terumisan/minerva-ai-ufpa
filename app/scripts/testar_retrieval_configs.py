"""Compara C1 (léxico puro), C2 (semântico puro) e C3 (híbrido RRF) no mesmo
dataset de avaliação usado por testar_retrieval.py, calculando as métricas
formais da Seção 9.3 da dissertação (Precision@5, Recall@5, MRR, nDCG@5) em
vez do hit-rate informal.

C4 (híbrido + atualização Web) não existe no protótipo ainda — fica de fora,
como já assumido no Apêndice A da dissertação.

Cada pergunta do dataset tem exatamente um chunk-fonte correto (chunk_id +
arquivo_fonte + trecho_fonte), então P@k/R@k/MRR/nDCG@k aqui usam a forma
fechada para relevância binária com 1 item relevante:
  P@k = 1/k se o chunk certo está entre os k primeiros, senão 0
  R@k = 1 se está entre os k primeiros, senão 0 (só há 1 item relevante)
  MRR = média de 1/posição (0 se não aparece entre os N recuperados)
  nDCG@k = 1/log2(pos+1) se pos<=k, senão 0 (IDCG@k = 1/log2(2) = 1)

Não chama o LLM — só consulta o Postgres, então roda rápido mesmo com as
720 perguntas x 3 configurações.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestao import conectar_banco  # noqa: E402
from minerva_hybrid import (  # noqa: E402
    _buscar_lexico,
    _buscar_semantico,
    buscar_em_documentos_postgres,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
OUT_PATH = DATA_DIR / "resultado_retrieval_configs.jsonl"

K = 5
N_CANDIDATOS = 10

CONFIGS = {
    "C1_lexico": lambda conn, pergunta: _buscar_lexico(conn, pergunta, limite=N_CANDIDATOS),
    "C2_semantico": lambda conn, pergunta: _buscar_semantico(conn, pergunta, limite=N_CANDIDATOS),
    "C3_hibrido": lambda conn, pergunta: buscar_em_documentos_postgres(conn, pergunta, limite=N_CANDIDATOS),
}


def _carregar_perguntas() -> list[dict]:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))["perguntas"]


def _posicao(fontes: list[dict], arquivo_fonte: str, trecho_fonte: str) -> int | None:
    for idx, f in enumerate(fontes, start=1):
        if f["titulo"] == arquivo_fonte and f["trecho"] == trecho_fonte:
            return idx
    return None


def _metricas(posicoes: list[int | None]) -> dict:
    n = len(posicoes)
    p_at_k = sum((1.0 / K) for pos in posicoes if pos is not None and pos <= K) / n
    r_at_k = sum(1 for pos in posicoes if pos is not None and pos <= K) / n
    mrr = sum((1.0 / pos) for pos in posicoes if pos is not None) / n
    ndcg_at_k = sum(
        (1.0 / math.log2(pos + 1)) for pos in posicoes if pos is not None and pos <= K
    ) / n
    return {
        "n": n,
        f"precision_at_{K}": round(p_at_k, 4),
        f"recall_at_{K}": round(r_at_k, 4),
        "mrr": round(mrr, 4),
        f"ndcg_at_{K}": round(ndcg_at_k, 4),
    }


def main() -> None:
    perguntas = _carregar_perguntas()
    conn = conectar_banco()

    registros = []
    posicoes_por_config: dict[str, list[int | None]] = {nome: [] for nome in CONFIGS}

    inicio = time.time()
    for i, item in enumerate(perguntas, start=1):
        registro = {
            "chunk_id": item["chunk_id"],
            "arquivo_fonte": item["arquivo_fonte"],
            "pergunta": item["pergunta"],
        }
        for nome, buscar in CONFIGS.items():
            fontes = buscar(conn, item["pergunta"])
            pos = _posicao(fontes, item["arquivo_fonte"], item["trecho_fonte"])
            registro[nome] = pos
            posicoes_por_config[nome].append(pos)
        registros.append(registro)

        if i % 50 == 0:
            decorrido = time.time() - inicio
            print(f"[{i}/{len(perguntas)}] {decorrido:.0f}s decorridos")

    conn.close()

    OUT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in registros) + "\n",
        encoding="utf-8",
    )

    print(f"\n=== Métricas de recuperação (k={K}, {len(perguntas)} perguntas) ===")
    resumo = {}
    for nome, posicoes in posicoes_por_config.items():
        m = _metricas(posicoes)
        resumo[nome] = m
        print(
            f"{nome}: P@{K}={m[f'precision_at_{K}']} "
            f"R@{K}={m[f'recall_at_{K}']} MRR={m['mrr']} nDCG@{K}={m[f'ndcg_at_{K}']}"
        )

    resumo_path = DATA_DIR / "resumo_retrieval_configs.json"
    resumo_path.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumo salvo em {resumo_path}")


if __name__ == "__main__":
    main()
