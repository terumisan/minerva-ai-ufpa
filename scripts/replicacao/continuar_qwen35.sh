#!/usr/bin/env bash
# Continuação de atualizar_qwen35.sh depois da troca: sobe o V7 com o Qwen3.5,
# confere que responde e roda as fases A e B.
set -euo pipefail
REPO="$HOME/minerva-ai-ufpa"; DIR="$REPO/scripts/replicacao"
QWEN="Qwen_Qwen3.5-4B-Q4_0.gguf"
exec > >(tee -a "$HOME/Downloads/atualizar_qwen35.log") 2>&1
echo "=== Continuação $(date -Is) ==="
docker compose -f "$REPO/docker-compose.yml" up -d ufpa_rag_llm
for i in $(seq 1 60); do curl -sf localhost:8002/health >/dev/null && break; sleep 3; done
curl -sf localhost:8002/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Responda em uma frase: o que é estágio supervisionado?"}],"max_tokens":60}' \
  | python3 -c "import json,sys;print('V7 respondeu:',json.load(sys.stdin)['choices'][0]['message']['content'])"
echo ">> 4. Fase A (protocolo da dissertação com Qwen3.5)"
MODELO="$QWEN" TAG=qwen35 FLAGS_MODELO=', "--jinja", "--reasoning-budget", "0"' bash "$DIR/replicar_d115.sh"
echo ">> 5. Fase B (V7 atual com Qwen3.5, em rodadas)"
TAG=qwen35 bash "$DIR/repetir_fase_b.sh"
echo "=== Fim $(date -Is) ==="
