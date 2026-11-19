"""Testa ponta-a-ponta (mesma cadeia de main.processar_pergunta: priority
router -> barreira institucional -> RAG genérico com LLM real) uma amostra
representativa do dataset de avaliação. Evita importar main.py (que exige
runtime do Streamlit) reimplementando a mesma cadeia com as funções puras.

Lento de propósito: cada pergunta que cai no RAG genérico chama o LLM local
(2-5min em CPU). Resumível — grava cada resultado assim que fica pronto.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestao import conectar_banco  # noqa: E402
from minerva_hybrid import responder_minerva  # noqa: E402
from minerva_priority_router import priority_answer  # noqa: E402
from prompts import consultar_modelo_local, pergunta_menciona_instituicao_externa  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
OUT_PATH = DATA_DIR / "resultado_e2e_amostra.jsonl"

TAMANHO_AMOSTRA = 150


def _carregar_perguntas() -> list[dict]:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))["perguntas"]


def _amostra_estratificada(perguntas: list[dict], tamanho: int) -> list[dict]:
    """Distribui a amostra proporcionalmente entre documentos-fonte, para
    não deixar um documento com muitos chunks (ex.: regimentos) dominar a
    amostra e documentos pequenos ficarem sem nenhuma pergunta testada.
    """
    por_arquivo: dict[str, list[dict]] = {}
    for p in perguntas:
        por_arquivo.setdefault(p["arquivo_fonte"], []).append(p)

    arquivos = sorted(por_arquivo)
    n_arquivos = len(arquivos)
    cota_base = max(1, tamanho // n_arquivos)

    amostra = []
    for arquivo in arquivos:
        itens = por_arquivo[arquivo]
        passo = max(1, len(itens) // cota_base)
        amostra.extend(itens[::passo][:cota_base])

    return amostra[:tamanho]


def _processados() -> set:
    if not OUT_PATH.exists():
        return set()
    ids = set()
    with OUT_PATH.open(encoding="utf-8") as f:
        for linha in f:
            try:
                ids.add(json.loads(linha)["chunk_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def main() -> None:
    perguntas = _carregar_perguntas()
    amostra = _amostra_estratificada(perguntas, TAMANHO_AMOSTRA)

    ja_feitos = _processados()
    pendentes = [p for p in amostra if p["chunk_id"] not in ja_feitos]

    print(f"Amostra: {len(amostra)} perguntas | já processadas: {len(ja_feitos)} | pendentes: {len(pendentes)}")

    inicio = time.time()
    for i, item in enumerate(pendentes, start=1):
        pergunta = item["pergunta"]
        t0 = time.time()

        resultado_priority = priority_answer(pergunta)

        if resultado_priority is not None:
            rota = "priority_router"
            resposta_obtida = resultado_priority
        elif pergunta_menciona_instituicao_externa(pergunta):
            rota = "barreira_externa"
            resposta_obtida = (
                "Meu escopo institucional está restrito à FCT/UFPA."
            )
        else:
            rota = "rag_generico"
            conn = None
            try:
                conn = conectar_banco()
                resposta_obtida = responder_minerva(
                    pergunta=pergunta, conn=conn, llm_func=consultar_modelo_local
                )
            finally:
                if conn is not None:
                    conn.close()

        tempo = time.time() - t0

        registro = {
            "chunk_id": item["chunk_id"],
            "arquivo_fonte": item["arquivo_fonte"],
            "pergunta": pergunta,
            "resposta_esperada": item["resposta_esperada"],
            "rota": rota,
            "resposta_obtida": resposta_obtida,
            "tempo_seg": round(tempo, 1),
        }

        with OUT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

        decorrido = time.time() - inicio
        media = decorrido / i
        eta_min = media * (len(pendentes) - i) / 60
        print(
            f"[{i}/{len(pendentes)}] rota={rota} tempo={tempo:.0f}s | "
            f"média {media:.0f}s/pergunta | ETA {eta_min:.0f} min"
        )

    print(f"\nConcluído: {len(pendentes)} perguntas processadas nesta execução.")


if __name__ == "__main__":
    main()
