#!/usr/bin/env bash
# Completa o juiz da Fase B: refaz julgamentos que falharam e avalia as
# respostas rag ainda sem julgamento, em rodadas de 6 min com modelo reiniciado.
set -uo pipefail
TAG=${TAG:-qwen35_20261118}
D=~/minerva-ai-ufpa/app/tests/data
E2E=resultado_e2e_v7_$TAG.jsonl; FID=resultado_fidelidade_v7_$TAG.jsonl
cd ~/minerva-ai-ufpa
touch "$D/$FID"  # 19/11: na primeira execução o arquivo do juiz ainda não existe
dono() { docker exec ufpa_rag_ui chown "$(id -u):$(id -g)" "/app/tests/data/$FID" "/app/tests/data/$E2E"; }
dono
cp "$D/$FID" "$D/${FID%.jsonl}_antes_pendentes.jsonl"
python3 - "$D/$FID" <<'PY'
import json, sys
p = sys.argv[1]; vistos = {}
for l in open(p, encoding="utf-8"):
    try: d = json.loads(l)
    except Exception: continue
    if not d.get("julgamento_falhou"): vistos[(d["chunk_id"], d["pergunta"])] = d
open(p, "w", encoding="utf-8").writelines(json.dumps(d, ensure_ascii=False) + "\n" for d in vistos.values())
print("julgamentos válidos mantidos:", len(vistos))
PY
pend() { python3 - "$D/$E2E" "$D/$FID" <<'PY'
import json, sys
e = {(d["chunk_id"], d["pergunta"]) for d in map(json.loads, open(sys.argv[1])) if d["rota"] == "rag_generico"}
f = {(d["chunk_id"], d["pergunta"]) for d in map(json.loads, open(sys.argv[2])) if not d.get("julgamento_falhou")}
print(len(e - f))
PY
}
for r in $(seq 1 12); do
  n=$(pend); echo ">> Rodada $r: pendentes $n"; [ "$n" -eq 0 ] && break
  docker restart ufpa_rag_llm >/dev/null; sleep 40
  docker compose exec -T ufpa_rag_ui timeout 360 python - <<PY
import sys; from pathlib import Path
sys.path.insert(0, "scripts")
import avaliar_fidelidade_llm as j
j.E2E_PATH = Path("tests/data/$E2E"); j.OUT_PATH = Path("tests/data/$FID")
j.main()
PY
  dono
  python3 - "$D/$FID" <<'PY'
import json, sys
p = sys.argv[1]; ok = []
for l in open(p, encoding="utf-8"):
    try: d = json.loads(l)
    except Exception: continue
    if not d.get("julgamento_falhou"): ok.append(json.dumps(d, ensure_ascii=False) + "\n")
open(p, "w", encoding="utf-8").writelines(ok)
PY
done
echo "=== Juiz completo: pendentes $(pend) ==="
