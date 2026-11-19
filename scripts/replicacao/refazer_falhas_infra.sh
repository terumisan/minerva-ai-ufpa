#!/usr/bin/env bash
# Remove da Fase B as respostas "Não localizei" dadas em < 2 s (modelo ainda
# indisponível logo após o reinício: ConnectionError, sem chamada ao LLM) e
# os julgamentos correspondentes; depois regenera e julga só essas perguntas.
set -uo pipefail
TAG=${TAG:-qwen35_20261119}
D=~/minerva-ai-ufpa/app/tests/data
E2E=$D/resultado_e2e_v7_$TAG.jsonl; FID=$D/resultado_fidelidade_v7_$TAG.jsonl
docker exec ufpa_rag_ui sh -c "chown $(id -u):$(id -g) /app/tests/data/resultado_*_v7_$TAG.jsonl"
cp "$E2E" "${E2E%.jsonl}_antes_refazer.jsonl"; cp "$FID" "${FID%.jsonl}_antes_refazer.jsonl"
python3 - "$E2E" "$FID" <<'PY'
import json, sys
e2e, fid = sys.argv[1:3]
E = [json.loads(l) for l in open(e2e)]
ruins = {(e["chunk_id"], e["pergunta"]) for e in E
         if e["tempo_seg"] < 2 and e["resposta_obtida"].startswith("Não localizei") and e["rota"] == "rag_generico"}
open(e2e, "w").writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in E if (e["chunk_id"], e["pergunta"]) not in ruins)
F = [json.loads(l) for l in open(fid)]
open(fid, "w").writelines(json.dumps(f, ensure_ascii=False) + "\n" for f in F if (f["chunk_id"], f["pergunta"]) not in ruins)
print(f"removidas {len(ruins)} respostas de falha de infraestrutura")
PY
cd ~/minerva-ai-ufpa/scripts/replicacao
echo ">> Reiniciando o modelo e esperando ele responder"
docker restart ufpa_rag_llm >/dev/null
until docker exec ufpa_rag_ui python -c "import requests,os;requests.post(os.environ.get('LLM_API_URL','http://ufpa_rag_llm:8002/v1/chat/completions'),json={'messages':[{'role':'user','content':'ok'}],'max_tokens':2},timeout=60).raise_for_status()" 2>/dev/null; do sleep 5; done
sleep 20  # folga: as primeiras chamadas logo após o reinício falhavam
echo ">> Regenerando só as perguntas removidas"
docker exec ufpa_rag_ui python - <<PY 2>&1 | grep -E "Amostra|Concluído"
import sys; from pathlib import Path
sys.path.insert(0, "scripts")
import testar_e2e_amostra as t
t.OUT_PATH = Path("tests/data/resultado_e2e_v7_$TAG.jsonl")
t.main()
PY
docker exec ufpa_rag_ui sh -c "chown $(id -u):$(id -g) /app/tests/data/resultado_*_v7_$TAG.jsonl"
TAG=$TAG bash juiz_pendentes.sh 2>&1 | grep -E "^(>>|===)"
