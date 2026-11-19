"""Roda as perguntas simuladas no fluxo real da Minerva e mede o resultado.

As perguntas (tests/data/perguntas_simuladas_20261113.json) são SIMULADAS,
no estilo de alunos; não vêm de usuários reais. O resultado mostra caminho,
tempo, documento/página citados e recusas, e serve para decidir o que
cadastrar no catálogo. Não homologa conteúdo nem vigência.

Uso (dentro do container, retomável — pula o que já está na saída):
  docker compose exec -T ufpa_rag_ui python scripts/avaliar_simuladas.py
  docker compose exec -T ufpa_rag_ui python scripts/avaliar_simuladas.py --estilos fora_escopo incompleta
  docker compose exec -T ufpa_rag_ui python scripts/avaliar_simuladas.py --resumo   # só recalcula o resumo
"""
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PERGUNTAS = ROOT / "tests" / "data" / "perguntas_simuladas_20261113.json"
SAIDA = ROOT / "tests" / "data" / "resultado_simuladas.jsonl"
RESUMO = ROOT / "tests" / "data" / "resumo_simuladas.json"

_CITACAO = re.compile(r"([\w.\-]+\.pdf) · páginas? físicas? (\d+)(?:\s*[–-]\s*(\d+))?")


def citacoes(resposta: str) -> list[tuple[str, int]]:
    """(documento, página) citados nos excertos da resposta."""
    achados = []
    for doc, ini, fim in _CITACAO.findall(resposta or ""):
        for p in range(int(ini), int(fim or ini) + 1):
            achados.append((doc, p))
    return achados


def avaliar(caso: dict, resposta: str, rota: str, fallback: str) -> dict:
    esp = caso["esperado"]
    cit = citacoes(resposta)
    recusou = resposta == fallback or rota == "barreira_institucional" or "Não localizei" in (resposta or "")
    r = {"citacoes": cit, "recusou": recusou}
    if esp["tipo"] == "catalogo":
        r["ok"] = bool(cit) and not recusou
    elif esp["tipo"] == "documental":
        docs = {d for d, _ in cit}
        r["doc_ok"] = esp["documento"] in docs
        r["pagina_ok"] = any(d == esp["documento"] and p in esp["paginas"] for d, p in cit)
        r["ok"] = r["pagina_ok"] if esp["paginas"] else r["doc_ok"]
    elif esp["tipo"] == "rota_fixa":
        r["ok"] = rota not in ("rag_generico", "rag_cache", "barreira_institucional")
    else:  # abstencao
        r["ok"] = recusou
    return r


def resumir(linhas: list[dict]) -> dict:
    por_estilo, tempos = defaultdict(Counter), defaultdict(list)
    sugestoes = []
    for x in linhas:
        por_estilo[x["estilo"]]["total"] += 1
        por_estilo[x["estilo"]]["ok"] += bool(x["avaliacao"].get("ok"))
        tempos[x["rota"]].append(x["ms"])
        if (x["esperado"]["tipo"] == "documental" and x["avaliacao"].get("pagina_ok")
                and x["rota"] == "rag_generico" and x["esperado"].get("entrada")):
            sugestoes.append({"entrada": x["esperado"]["entrada"], "nova_variacao": x["pergunta"],
                              "ms_atual": x["ms"]})

    def pct(v, q):
        v = sorted(v)
        return v[min(len(v) - 1, int(q * len(v)))] if v else None

    return {
        "aviso": "perguntas simuladas; não são de usuários reais",
        "total": len(linhas),
        "acerto_por_estilo": {k: f"{v['ok']}/{v['total']}" for k, v in por_estilo.items()},
        "tempo_ms_por_rota": {k: {"n": len(v), "p50": pct(v, .5), "p95": pct(v, .95)} for k, v in tempos.items()},
        "falhas": [{"id": x["id"], "estilo": x["estilo"], "pergunta": x["pergunta"], "rota": x["rota"],
                    "citacoes": x["avaliacao"]["citacoes"][:4], "esperado": x["esperado"]}
                   for x in linhas if not x["avaliacao"].get("ok")],
        "sugestoes_variacoes_catalogo": sugestoes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--estilos", nargs="*", help="só estes estilos")
    ap.add_argument("--limite", type=int, help="no máximo N perguntas novas")
    ap.add_argument("--resumo", action="store_true", help="só recalcula o resumo")
    args = ap.parse_args()

    casos = json.loads(PERGUNTAS.read_text(encoding="utf-8"))["perguntas"]
    feitos = {}
    if SAIDA.exists():
        for linha in SAIDA.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                x = json.loads(linha)
                feitos[x["id"]] = x

    if not args.resumo:
        import minerva_hybrid as rag
        from minerva_priority_router import classify_question, priority_answer
        from prompts import consultar_modelo_local, pergunta_menciona_instituicao_externa
        from scripts.ingestao import conectar_banco

        def llm(prompt, max_tokens=None):
            if max_tokens is None:
                return consultar_modelo_local(prompt)
            return consultar_modelo_local(prompt, max_tokens=max_tokens)

        conn = conectar_banco()
        pendentes = [c for c in casos if c["id"] not in feitos
                     and (not args.estilos or c["estilo"] in args.estilos)]
        if args.limite:
            pendentes = pendentes[:args.limite]
        with SAIDA.open("a", encoding="utf-8") as out:
            for i, caso in enumerate(pendentes, 1):
                q = caso["pergunta"]
                t0 = time.perf_counter()
                if pergunta_menciona_instituicao_externa(q):
                    resposta, rota = "", "barreira_institucional"
                else:
                    fixa = priority_answer(q)
                    if fixa is not None:
                        resposta, rota = fixa, classify_question(q) or "dataset_ou_basico"
                    else:
                        try:
                            resposta = rag.responder_minerva(pergunta=q, conn=conn, llm_func=llm)
                        except Exception as ex:  # registra e segue
                            conn.rollback()
                            resposta = f"ERRO: {type(ex).__name__}"
                        rota = "rag_generico"
                ms = round((time.perf_counter() - t0) * 1000)
                x = {**caso, "rota": rota, "ms": ms, "resposta": resposta[:3000],
                     "avaliacao": avaliar(caso, resposta, rota, rag.fallback_sem_base())}
                out.write(json.dumps(x, ensure_ascii=False) + "\n")
                out.flush()
                feitos[caso["id"]] = x
                print(f"[{i}/{len(pendentes)}] {caso['id']} {rota} {ms/1000:.1f}s "
                      f"{'OK' if x['avaliacao'].get('ok') else 'FALHA'} | {q[:60]}", flush=True)
        conn.close()

    resumo = resumir([feitos[c["id"]] for c in casos if c["id"] in feitos])
    RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: resumo[k] for k in ("total", "acerto_por_estilo", "tempo_ms_por_rota")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
