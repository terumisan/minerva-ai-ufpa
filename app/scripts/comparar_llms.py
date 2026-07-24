"""Roda a mesma amostra de perguntas pelo pipeline real da Minerva (priority
router -> barreira -> RAG genérico) contra QUALQUER modelo que esteja
carregado no momento em ufpa_rag_llm — usado para comparar dois modelos
(rodar uma vez por modelo, trocando o command do docker-compose entre as
execuções). Grava em tests/data/comparacao_<tag>.jsonl.
"""
from __future__ import annotations

import argparse
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
AMOSTRA_PATH = DATA_DIR / "amostra_comparacao_modelos.json"


def main(tag: str) -> None:
    amostra = json.loads(AMOSTRA_PATH.read_text(encoding="utf-8"))
    out_path = DATA_DIR / f"comparacao_{tag}.jsonl"

    resultados = []
    for item in amostra:
        pergunta = item["pergunta"]
        t0 = time.time()

        resultado_priority = priority_answer(pergunta)
        if resultado_priority is not None:
            rota, resposta = "priority_router", resultado_priority
        elif pergunta_menciona_instituicao_externa(pergunta):
            rota, resposta = "barreira_externa", "Escopo restrito à FCT/UFPA."
        else:
            conn = conectar_banco()
            try:
                resposta = responder_minerva(pergunta=pergunta, conn=conn, llm_func=consultar_modelo_local)
            finally:
                conn.close()
            rota = "rag_generico"

        tempo = time.time() - t0
        registro = {
            "arquivo_fonte": item["arquivo_fonte"],
            "pergunta": pergunta,
            "resposta_esperada": item["resposta_esperada"],
            "rota": rota,
            "tempo_seg": round(tempo, 1),
            "resposta": resposta,
        }
        resultados.append(registro)
        print(f"[{rota} {tempo:.0f}s] {pergunta}")

    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resultados) + "\n",
        encoding="utf-8",
    )
    print(f"\nSalvo em {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Identificador do modelo em teste (ex.: qwen25_7b, qwen3_4b)")
    args = parser.parse_args()
    main(args.tag)
