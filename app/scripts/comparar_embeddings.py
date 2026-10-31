"""Compara modelos de embedding multilíngue (fastembed) na tarefa real de
retrieval da Minerva, usando o dataset de avaliação (720 perguntas com chunk
de origem conhecido) — sem tocar no Postgres de produção. Só a busca
SEMÂNTICA é comparada aqui (a busca léxica não muda com o modelo).

Modelos multilíngues disponíveis nesta versão do fastembed (0.8.0) capazes de
Português: paraphrase-multilingual-MiniLM-L12-v2 (atual, 384d),
paraphrase-multilingual-mpnet-base-v2 (768d), multilingual-e5-large (1024d).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
CACHE_DIR = "/app/.fastembed_cache"

MODELOS = [
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "intfloat/multilingual-e5-large",
]


def _hit_rate(sim: np.ndarray, chunk_ids_unicos: list[int], indice_certo: np.ndarray, k: int) -> float:
    topk = np.argsort(-sim, axis=1)[:, :k]
    acertos = (topk == indice_certo[:, None]).any(axis=1)
    return float(acertos.mean())


def main() -> None:
    perguntas = json.loads(EVAL_PATH.read_text(encoding="utf-8"))["perguntas"]

    # Universo de chunks únicos (trecho_fonte) — cada pergunta sabe a qual
    # chunk pertence; simula o "banco" só com os chunks realmente usados
    # no eval, suficiente para comparar RANKING relativo entre modelos.
    trechos_unicos = []
    trecho_para_indice = {}
    chunk_id_por_pergunta = []
    for p in perguntas:
        chave = (p["arquivo_fonte"], p["trecho_fonte"])
        if chave not in trecho_para_indice:
            trecho_para_indice[chave] = len(trechos_unicos)
            trechos_unicos.append(p["trecho_fonte"])
        chunk_id_por_pergunta.append(trecho_para_indice[chave])

    indice_certo = np.array(chunk_id_por_pergunta)
    textos_perguntas = [p["pergunta"] for p in perguntas]

    print(f"{len(perguntas)} perguntas | {len(trechos_unicos)} chunks únicos\n")

    for nome_modelo in MODELOS:
        print(f"=== {nome_modelo} ===")
        t0 = time.time()
        modelo = TextEmbedding(model_name=nome_modelo, cache_dir=CACHE_DIR)

        emb_chunks = np.array(list(modelo.passage_embed(trechos_unicos)))
        emb_perguntas = np.array(list(modelo.query_embed(textos_perguntas)))
        t_embed = time.time() - t0

        # cosseno: os vetores do fastembed já vêm normalizados (norma 1),
        # então o produto interno equivale à similaridade de cosseno.
        sim = emb_perguntas @ emb_chunks.T

        r1 = _hit_rate(sim, trechos_unicos, indice_certo, 1)
        r3 = _hit_rate(sim, trechos_unicos, indice_certo, 3)
        r6 = _hit_rate(sim, trechos_unicos, indice_certo, 6)

        print(f"hit@1: {r1*100:.1f}% | hit@3: {r3*100:.1f}% | hit@6: {r6*100:.1f}% | tempo: {t_embed:.1f}s\n")

        del modelo, emb_chunks, emb_perguntas, sim


if __name__ == "__main__":
    main()
