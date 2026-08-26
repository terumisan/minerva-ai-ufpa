"""Juiz automático (LLM-as-judge) para fidelidade e alucinação, Equações
(8)-(11) da dissertação — Context Precision/Recall, Faithfulness (F) e taxa
de alucinação derivada (H = 1-F).

Roda sobre resultado_e2e_amostra.jsonl (ver testar_e2e_amostra.py), só nas
linhas rota == "rag_generico" (únicas com contexto recuperado — as de
priority_router são resposta determinística por regra, sem RAG).

Metodologia (documentar na dissertação, Seção 9.4/9.7):
- Juiz = o próprio Qwen2.5-7B-Instruct local que gera as respostas da
  Minerva (mesma justificativa de "execução local" da arquitetura). Ponto
  de atenção: vies de autoavaliação (o modelo pode ser mais tolerante com
  o próprio estilo de resposta) — não é um juiz independente como GPT-4/
  Claude usados em RAGAs/ARES. Reportar como limitação, não substituir por
  avaliação humana formal com usuários (que é o que está sendo evitado).
- O contexto usado para julgar fidelidade é recuperado de novo, via a
  mesma função buscar_em_documentos_postgres usada em produção (não
  chama o LLM — é determinístico), então reflete exatamente o que o
  modelo viu ao gerar resposta_obtida.
- Correção factual vs. gabarito (resposta_esperada) também é julgada pelo
  mesmo LLM, com o mesmo aviso de viés.

Resumível: grava cada resultado assim que fica pronto, pula linhas já
avaliadas numa próxima execução.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestao import conectar_banco  # noqa: E402
from minerva_hybrid import buscar_em_documentos_postgres  # noqa: E402

LLM_API_URL = os.getenv("LLM_API_URL", "http://ufpa_rag_llm:8002/v1/chat/completions")

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
E2E_PATH = DATA_DIR / "resultado_e2e_amostra.jsonl"
OUT_PATH = DATA_DIR / "resultado_fidelidade_llm.jsonl"

PROMPT_SISTEMA = """Você avalia respostas de um chatbot institucional da FCT/UFPA comparando-as com o contexto documental que o chatbot recebeu e com uma resposta de referência (gabarito).

Tarefas:
1. Divida a RESPOSTA em afirmações atômicas (fatos isolados e verificáveis). Para cada uma, diga se ela está sustentada pelo CONTEXTO fornecido (sustentada=true) ou não (sustentada=false — inclui invenção, extrapolação ou informação de fora do contexto).
2. Diga se a RESPOSTA é uma abstenção (recusa a responder por falta de evidência, ex.: "não localizei informação suficiente").
3. Compare a RESPOSTA com o GABARITO e classifique correta_vs_gabarito como "sim" (compatível em substância), "parcial" (parcialmente correta ou incompleta) ou "nao" (incorreta ou contradiz o gabarito).

Responda SOMENTE em JSON válido, neste formato exato:
{"claims": [{"texto": "...", "sustentada": true}], "abstencao": false, "correta_vs_gabarito": "sim"}

Se a RESPOSTA for uma abstenção, "claims" deve ser uma lista vazia [] e "abstencao" true.
"""


def _pedir_julgamento(pergunta: str, resposta: str, gabarito: str, contexto: str) -> dict | None:
    prompt_usuario = (
        f"PERGUNTA:\n{pergunta}\n\n"
        f"RESPOSTA do chatbot:\n{resposta}\n\n"
        f"GABARITO (referência):\n{gabarito}\n\n"
        f"CONTEXTO recuperado (o que o chatbot viu):\n{contexto if contexto else '(nenhum trecho recuperado)'}"
    )
    payload = {
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": 0.0,
        "max_tokens": 700,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    resp = requests.post(LLM_API_URL, json=payload, timeout=300)
    resp.raise_for_status()
    conteudo = resp.json()["choices"][0]["message"]["content"].strip()

    match = re.search(r"\{.*\}", conteudo, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _carregar_index_gabarito() -> dict:
    perguntas = json.loads(EVAL_PATH.read_text(encoding="utf-8"))["perguntas"]
    return {(item["chunk_id"], item["pergunta"]): item["trecho_fonte"] for item in perguntas}


def _ja_avaliados() -> set[tuple]:
    if not OUT_PATH.exists():
        return set()
    vistos = set()
    with OUT_PATH.open(encoding="utf-8") as f:
        for linha in f:
            try:
                r = json.loads(linha)
                vistos.add((r["chunk_id"], r["pergunta"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return vistos


def main() -> None:
    linhas_e2e = [
        json.loads(l) for l in E2E_PATH.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    linhas_rag = [l for l in linhas_e2e if l.get("rota") == "rag_generico"]
    print(f"Linhas e2e totais: {len(linhas_e2e)} | rota=rag_generico: {len(linhas_rag)}")

    index_gabarito = _carregar_index_gabarito()
    ja_feitos = _ja_avaliados()
    pendentes = [l for l in linhas_rag if (l["chunk_id"], l["pergunta"]) not in ja_feitos]
    print(f"Já avaliados: {len(ja_feitos)} | pendentes: {len(pendentes)}")

    conn = conectar_banco()
    inicio = time.time()

    for i, item in enumerate(pendentes, start=1):
        pergunta = item["pergunta"]
        fontes = buscar_em_documentos_postgres(conn, pergunta)
        contexto = "\n\n".join(f"Fonte: {f['titulo']}\nTrecho: {f['trecho']}" for f in fontes)

        trecho_fonte = index_gabarito.get((item["chunk_id"], pergunta), "")
        gold_no_contexto = any(
            f["titulo"] == item["arquivo_fonte"] and f["trecho"] == trecho_fonte for f in fontes
        )

        julgamento = None
        try:
            julgamento = _pedir_julgamento(
                pergunta, item["resposta_obtida"], item["resposta_esperada"], contexto
            )
        except Exception as exc:
            print(f"[{i}/{len(pendentes)}] erro no juiz: {exc}")

        claims = (julgamento or {}).get("claims", [])
        n_claims = len(claims)
        n_sustentadas = sum(1 for c in claims if c.get("sustentada"))
        fidelidade = (n_sustentadas / n_claims) if n_claims else None

        registro = {
            "chunk_id": item["chunk_id"],
            "arquivo_fonte": item["arquivo_fonte"],
            "pergunta": pergunta,
            "gold_no_contexto_recuperado": gold_no_contexto,
            "n_claims": n_claims,
            "n_claims_sustentadas": n_sustentadas,
            "fidelidade": fidelidade,
            "abstencao": (julgamento or {}).get("abstencao"),
            "correta_vs_gabarito": (julgamento or {}).get("correta_vs_gabarito"),
            "julgamento_falhou": julgamento is None,
        }

        with OUT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

        decorrido = time.time() - inicio
        media = decorrido / i
        eta_min = media * (len(pendentes) - i) / 60
        print(
            f"[{i}/{len(pendentes)}] fidelidade={fidelidade} "
            f"correta={registro['correta_vs_gabarito']} | média {media:.0f}s/pergunta | ETA {eta_min:.0f} min"
        )

    conn.close()

    todos = [
        json.loads(l) for l in OUT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()
    ] if OUT_PATH.exists() else []
    validos = [r for r in todos if r["fidelidade"] is not None]
    if validos:
        fidelidade_media = sum(r["fidelidade"] for r in validos) / len(validos)
        print(f"\n=== Resumo ({len(todos)} avaliados, {len(validos)} com resposta não-abstenção) ===")
        print(f"Fidelidade média: {fidelidade_media:.4f}")
        print(f"Alucinação derivada (1-F): {1 - fidelidade_media:.4f}")
        n_corretas = sum(1 for r in todos if r["correta_vs_gabarito"] == "sim")
        n_abstencoes = sum(1 for r in todos if r["abstencao"])
        print(f"Correta vs. gabarito ('sim'): {n_corretas}/{len(todos)} ({100*n_corretas/len(todos):.1f}%)")
        print(f"Abstenções (base era respondível): {n_abstencoes}/{len(todos)} ({100*n_abstencoes/len(todos):.1f}%)")
        gold_recall = sum(1 for r in todos if r["gold_no_contexto_recuperado"]) / len(todos)
        print(f"Context recall (gabarito entre os recuperados): {gold_recall:.4f}")


if __name__ == "__main__":
    main()
