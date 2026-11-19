"""Reclassifica as 'abstenções' do juiz que são, na verdade, exibição de excertos.

Desde 15/11 a Minerva mostra só os trechos das normas (sem prosa). O juiz LLM
marca essas saídas como abstenção. Aqui medimos, sem LLM, se os excertos
exibidos contêm o gabarito (cobertura de palavras de conteúdo).
Uso: python3 reavaliar_excertos.py resultado_e2e.jsonl resultado_fidelidade.jsonl
"""
import json, re, sys, unicodedata
from collections import Counter

VAZIAS = set("a o e de da do das dos em que para os as no na nos nas um uma se ser por com ao".split())
LIMIAR = 0.75


def n(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t))


def cobertura(gabarito, obtida):
    g = set(n(gabarito).split()) - VAZIAS
    return len(g & set(n(obtida).split())) / max(len(g), 1)


def main(e2e, fid):
    E = {(d["chunk_id"], d["pergunta"]): d for d in map(json.loads, open(e2e))}
    F = {(d["chunk_id"], d["pergunta"]): d for d in map(json.loads, open(fid)) if not d.get("julgamento_falhou")}
    cls = Counter(); casos = []
    for k, f in F.items():
        e = E[k]
        if not f["abstencao"]:
            cls["respondeu_" + f["correta_vs_gabarito"]] += 1
            continue
        excerto = e["resposta_obtida"].startswith("Excertos")
        c = cobertura(e["resposta_esperada"], e["resposta_obtida"])
        if excerto and c >= LIMIAR:
            rot = "excerto_contem_gabarito"
        elif excerto:
            rot = "excerto_sem_gabarito"
        else:
            rot = "abstencao_real"
        cls[rot] += 1
        casos.append((rot, round(c, 2), f["gold_no_contexto_recuperado"], e["arquivo_fonte"], e["pergunta"]))
    total = sum(cls.values())
    uteis = cls["respondeu_sim"] + cls["excerto_contem_gabarito"]
    print(f"Julgadas: {total}")
    for k, v in sorted(cls.items()):
        print(f"  {k:26s} {v}")
    print(f"Resposta correta OU excerto com o gabarito: {uteis}/{total} ({100*uteis/total:.0f}%)")
    print("\nCasos não respondidos:")
    for c in sorted(casos):
        print("  ", *c)


if __name__ == "__main__":
    main(*sys.argv[1:3])
