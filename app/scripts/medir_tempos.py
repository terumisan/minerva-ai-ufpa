"""Mede onde vai o tempo das respostas da Minerva (busca x leitura do prompt
x geração), usando os tempos que o próprio llama.cpp devolve em "timings".

Uso: docker exec ufpa_rag_ui python scripts/medir_tempos.py [N]
Usa as N primeiras perguntas da Fase B que foram para o RAG (padrão 12).
"""
import json
import statistics as st
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import minerva_hybrid as rag  # noqa: E402
import prompts  # noqa: E402
from scripts.ingestao import conectar_banco  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
ARQ = sorted(Path("tests/data").glob("resultado_e2e_v7_qwen35_*.jsonl"))[-1]
perguntas = []
for linha in ARQ.open(encoding="utf-8"):
    d = json.loads(linha)
    if d["rota"] == "rag_generico" and d["pergunta"] not in perguntas:
        perguntas.append(d["pergunta"])
perguntas = perguntas[:N]

chamadas = []
_post = prompts.http_session.post


def post_medido(*a, **k):
    r = _post(*a, **k)
    try:
        t = r.json().get("timings", {})
        chamadas.append({"prompt_n": t.get("prompt_n", 0), "prompt_ms": t.get("prompt_ms", 0),
                         "cache_n": t.get("cache_n", 0),
                         "gerados_n": t.get("predicted_n", 0), "gerados_ms": t.get("predicted_ms", 0)})
    except Exception:
        pass
    return r


prompts.http_session.post = post_medido
_busca = rag.buscar_em_documentos_postgres
tempos_busca = []


def busca_medida(*a, **k):
    t0 = time.monotonic()
    r = _busca(*a, **k)
    tempos_busca.append(time.monotonic() - t0)
    return r


rag.buscar_em_documentos_postgres = busca_medida

linhas = []
with closing(conectar_banco()) as conn:
    for i, p in enumerate(perguntas, 1):
        antes = len(chamadas)
        t0 = time.monotonic()
        rag.responder_minerva(p, conn=conn, llm_func=prompts.consultar_modelo_local)
        total = time.monotonic() - t0
        cs = chamadas[antes:]
        linha = {"total": total, "busca": tempos_busca[-1] if tempos_busca else 0,
                 "leitura": sum(c["prompt_ms"] for c in cs) / 1000,
                 "geracao": sum(c["gerados_ms"] for c in cs) / 1000,
                 "tok_prompt": sum(c["prompt_n"] for c in cs), "tok_cache": sum(c["cache_n"] for c in cs),
                 "tok_gerados": sum(c["gerados_n"] for c in cs), "chamadas": len(cs)}
        linhas.append(linha)
        print(f"[{i}/{len(perguntas)}] {total:5.1f}s  busca {linha['busca']:4.1f}s  "
              f"leitura {linha['leitura']:5.1f}s ({linha['tok_prompt']} tok, {linha['tok_cache']} do cache)  "
              f"geração {linha['geracao']:5.1f}s ({linha['tok_gerados']} tok)  | {p[:50]}", flush=True)

m = lambda k: st.mean(x[k] for x in linhas)  # noqa: E731
print("\nMÉDIAS")
print(f"  total {m('total'):.1f}s = busca {m('busca'):.1f}s + leitura do prompt {m('leitura'):.1f}s "
      f"+ geração {m('geracao'):.1f}s + resto {m('total') - m('busca') - m('leitura') - m('geracao'):.1f}s")
print(f"  tokens: prompt {m('tok_prompt'):.0f} (cache {m('tok_cache'):.0f}), gerados {m('tok_gerados'):.0f}")
if m('leitura'):
    print(f"  velocidade: leitura {m('tok_prompt') / m('leitura'):.0f} tok/s, "
          f"geração {m('tok_gerados') / max(m('geracao'), 1e-9):.1f} tok/s")
