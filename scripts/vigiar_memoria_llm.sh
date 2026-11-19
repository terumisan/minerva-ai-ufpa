#!/usr/bin/env bash
# Reinicia o ufpa_rag_llm antes que o vazamento de memória do llama.cpp o
# leve ao OOM (14/11/2026: morto aos 41 min com teto de 6 GiB e aos 32 min com
# 9 GiB, sob perguntas seguidas). Rodado a cada 2 min pelo timer
# ufpa_rag_vigia_llm.timer (ver instalar_vigia_memoria_llm.sh).
#
# Regra: acima de LIMITE_GIB (padrão 5,0) reinicia se o modelo estiver ocioso;
# acima de LIMITE_FORCADO_GIB (padrão 5,6, perto do teto de 6 GiB) reinicia
# mesmo ocupado, porque o OOM derrubaria a pergunta de qualquer forma.
set -uo pipefail
C=ufpa_rag_llm
LIMITE_GIB="${LIMITE_GIB:-5.0}"
LIMITE_FORCADO_GIB="${LIMITE_FORCADO_GIB:-5.6}"
URL="${LLM_URL:-http://localhost:8002}"

[ "$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" = "true" ] || exit 0
uso=$(docker stats --no-stream --format '{{.MemUsage}}' "$C" | awk '{print $1}')
gib=$(python3 - "$uso" <<'PY'
import re, sys
m = re.match(r'([\d.]+)\s*([KMGT]?i?B)', sys.argv[1])
v, u = float(m.group(1)), m.group(2)
f = {'B': 1/2**30, 'KiB': 1/2**20, 'MiB': 1/2**10, 'GiB': 1, 'TiB': 2**10,
     'kB': 1e3/2**30, 'MB': 1e6/2**30, 'GB': 1e9/2**30}.get(u, 1)
print(f"{v*f:.2f}")
PY
)
acima() { python3 -c "import sys; sys.exit(0 if $gib >= $1 else 1)"; }
acima "$LIMITE_GIB" || exit 0

ocupado=$(curl -sf --max-time 5 "$URL/slots" | python3 -c "
import json, sys
try:
    print(any(s.get('is_processing') for s in json.load(sys.stdin)))
except Exception:
    print('desconhecido')" 2>/dev/null || echo desconhecido)

if [ "$ocupado" = "False" ] || acima "$LIMITE_FORCADO_GIB"; then
  echo "ufpa_rag_llm com ${gib} GiB (ocupado=${ocupado}); reiniciando para liberar memória"
  docker restart "$C" >/dev/null
else
  echo "ufpa_rag_llm com ${gib} GiB, mas ocupado=${ocupado}; tenta de novo no próximo ciclo"
fi
