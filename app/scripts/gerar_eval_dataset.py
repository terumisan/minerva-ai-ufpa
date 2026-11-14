"""Gera um dataset de avaliação (pergunta + resposta esperada + fonte) a
partir dos chunks já ingeridos em documentos_ufpa, usando o próprio LLM
local (Qwen2.5-7B via llama.cpp) para produzir perguntas plausíveis de
aluno e a resposta grounded no trecho.

Não é o dataset de produção (minerva_dataset.json) — é material de
avaliação para medir e depois melhorar a qualidade das respostas da
Minerva (ver app/scripts/testar_eval_dataset.py).

Resumível: grava cada chunk processado incrementalmente em JSONL
(EVAL_RAW_PATH) e pula chunks já processados se rodar de novo.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingestao import conectar_banco  # noqa: E402

LLM_API_URL = os.getenv("LLM_API_URL", "http://ufpa_rag_llm:8002/v1/chat/completions")

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_PATH = OUT_DIR / "eval_qa_raw.jsonl"
FINAL_PATH = OUT_DIR / "eval_minerva_qa.json"

# Regimento_UFPA_FCT.pdf era um duplicado exato (MD5 idêntico) de
# RegimentoGeral.pdf — removido de documentos/ e do banco (ver limpeza de
# consistência de dados). Só RegimentoGeral.pdf sobrevive agora, então não
# há mais duplicata pra pular aqui.
#
# CalendarioAcademico2026.pdf: extração de tabela vira texto embaralhado
# (datas e rótulos fora de ordem) — o LLM "adivinha" pares errados a partir
# disso (confirmado: gerou "Finados: 15/10" em vez de 02/11). Além disso,
# perguntas de calendário já são desviadas para o site da PROEG por
# minerva_priority_router.py (nunca usam este PDF), então gerar QA daqui
# não teria valor de avaliação real.
ARQUIVOS_A_PULAR = {"CalendarioAcademico2026.pdf"}

PROMPT_SISTEMA = """Você gera pares de pergunta-e-resposta para testar um chatbot acadêmico da FCT/UFPA (Faculdade de Computação e Telecomunicações, Universidade Federal do Pará).

Dado um trecho de um documento oficial, gere perguntas que um aluno real faria e cuja resposta esteja 100% contida no trecho — nunca invente informação fora dele.

Responda SOMENTE em JSON válido, neste formato exato:
{"perguntas": [{"pergunta": "...", "resposta": "..."}]}

Regras:
- Pergunta: linguagem natural de aluno (não cite "o trecho" ou "o documento").
- Resposta: direta, objetiva, baseada só no trecho, no máximo 3 frases.
- Se o trecho não tiver conteúdo perguntável (ex.: só título/numeração), devolva {"perguntas": []}.
"""


def _pedir_llm(trecho: str, n_perguntas: int) -> list[dict]:
    prompt_usuario = (
        f"Gere {n_perguntas} pergunta(s) e resposta(s) a partir deste trecho:\n\n"
        f"{trecho}"
    )
    payload = {
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": 0.4,
        "max_tokens": 320,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    resp = requests.post(LLM_API_URL, json=payload, timeout=300)
    resp.raise_for_status()
    conteudo = resp.json()["choices"][0]["message"]["content"].strip()

    # O modelo às vezes envolve o JSON em ```json ... ``` apesar da instrução.
    match = re.search(r"\{.*\}", conteudo, flags=re.DOTALL)
    if not match:
        return []

    try:
        dados = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    perguntas = dados.get("perguntas", [])
    return [
        p for p in perguntas
        if isinstance(p, dict) and p.get("pergunta") and p.get("resposta")
    ]


def _ja_processados() -> set[int]:
    if not RAW_PATH.exists():
        return set()
    ids = set()
    with RAW_PATH.open(encoding="utf-8") as f:
        for linha in f:
            try:
                ids.add(json.loads(linha)["chunk_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def main() -> None:
    conn = conectar_banco()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nome_arquivo, conteudo FROM documentos_ufpa "
        "WHERE nome_arquivo != ALL(%s) ORDER BY nome_arquivo, id;",
        (list(ARQUIVOS_A_PULAR),),
    )
    chunks = cur.fetchall()
    cur.close()
    conn.close()

    processados = _ja_processados()
    pendentes = [c for c in chunks if c[0] not in processados]

    print(f"Total de chunks: {len(chunks)} | já processados: {len(processados)} | pendentes: {len(pendentes)}")

    inicio = time.time()
    for i, (chunk_id, arquivo, conteudo) in enumerate(pendentes, start=1):
        n_perguntas = 1 if len(conteudo) < 300 else 2

        try:
            pares = _pedir_llm(conteudo, n_perguntas)
        except Exception as exc:
            print(f"[{i}/{len(pendentes)}] chunk {chunk_id} ({arquivo}): erro {exc}")
            pares = []

        with RAW_PATH.open("a", encoding="utf-8") as f:
            for par in pares:
                f.write(json.dumps({
                    "chunk_id": chunk_id,
                    "arquivo_fonte": arquivo,
                    "trecho_fonte": conteudo,
                    "pergunta": par["pergunta"].strip(),
                    "resposta_esperada": par["resposta"].strip(),
                }, ensure_ascii=False) + "\n")

            if not pares:
                # marca o chunk como processado mesmo sem gerar par, para não
                # tentar de novo numa próxima execução resumida.
                f.write(json.dumps({"chunk_id": chunk_id, "vazio": True}, ensure_ascii=False) + "\n")

        decorrido = time.time() - inicio
        media = decorrido / i
        eta_min = media * (len(pendentes) - i) / 60
        print(
            f"[{i}/{len(pendentes)}] chunk {chunk_id} ({arquivo}): "
            f"{len(pares)} par(es) | média {media:.0f}s/chunk | ETA {eta_min:.0f} min"
        )

    # Consolida em um único array JSON (formato final para o harness de teste).
    finais = []
    contador = 0
    with RAW_PATH.open(encoding="utf-8") as f:
        for linha in f:
            registro = json.loads(linha)
            if registro.get("vazio"):
                continue
            contador += 1
            registro["id"] = f"EVAL_{contador:04d}"
            finais.append(registro)

    FINAL_PATH.write_text(
        json.dumps({"total": len(finais), "perguntas": finais}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nConcluído: {len(finais)} pares de pergunta/resposta em {FINAL_PATH}")


if __name__ == "__main__":
    main()
