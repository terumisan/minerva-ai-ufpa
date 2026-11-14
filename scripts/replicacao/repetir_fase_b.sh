#!/usr/bin/env bash
# Fase B (V7 atual + modelo configurado no .env) da replicação D115.
# Falhas anteriores (14/11): o llama-server do V7 vaza memória sob carga
# contínua (cache de graphs) e foi morto por OOM aos 41 min (teto 6 GiB) e
# aos 32 min (teto 9 GiB). Solução: rodar em rodadas de 12 min, reiniciando
# o modelo antes de cada rodada. Os scripts de geração e juiz retomam de onde
# pararam. Se o modelo reiniciar durante uma rodada, as linhas gravadas
# nela são descartadas e a rodada é refeita. Teto de memória do V7 inalterado.
set -uo pipefail
REPO="$HOME/minerva-ai-ufpa"
TAG="${TAG:-gemma4}"
SAIDA="$HOME/Downloads/replicacao_d115_$TAG"
LOG="$HOME/Downloads/replicacao_fase_b_$TAG.log"
mkdir -p "$SAIDA"
DADOS="$REPO/app/tests/data"
E2E=resultado_e2e_v7_${TAG}.jsonl
FID=resultado_fidelidade_v7_${TAG}.jsonl
RODADA_S=720
DC=(docker compose -f "$REPO/docker-compose.yml")
exec > >(tee -a "$LOG") 2>&1
echo "=== Início Fase B (rodadas) $(date -Is) ==="

for f in "$E2E" "$FID"; do
  [ -f "$DADOS/$f" ] && mv "$DADOS/$f" "$DADOS/${f%.jsonl}_INVALIDO_$(date +%H%M%S).jsonl"
done
rm -f "$SAIDA/$E2E" "$SAIDA/$FID" "$SAIDA/resumo_juiz_v7.txt"

reiniciar_e_esperar() {
  docker restart ufpa_rag_llm >/dev/null
  for i in $(seq 1 60); do
    if "${DC[@]}" exec -T ufpa_rag_ui python - >/dev/null 2>&1 <<'PY'
import os, requests
u = os.environ.get("LLM_API_URL", "http://ufpa_rag_llm:8002/v1/chat/completions")
requests.post(u, json={"messages":[{"role":"user","content":"ok"}],"max_tokens":2}, timeout=60).raise_for_status()
PY
    then INICIO=$(docker inspect -f '{{.State.StartedAt}}' ufpa_rag_llm); return 0; fi
    sleep 5
  done
  echo "MODELO_NAO_RESPONDE"; exit 1
}
linhas() { [ -f "$1" ] && wc -l < "$1" || echo 0; }
limpar_parcial() {  # remove linha final incompleta, se houver
  [ -f "$1" ] || return 0
  python3 - "$1" <<'PY'
import json, sys
p = sys.argv[1]; ok = []
for l in open(p, encoding="utf-8"):
    try: json.loads(l); ok.append(l if l.endswith("\n") else l + "\n")
    except Exception: pass
open(p, "w", encoding="utf-8").writelines(ok)
PY
}

# $1 = arquivo de saída, $2 = total esperado, $3 = código python da etapa
etapa() {
  local arq="$1" total="$2" codigo="$3" r=0
  while :; do
    limpar_parcial "$arq"
    local antes; antes=$(linhas "$arq")
    [ "$antes" -ge "$total" ] && break
    r=$((r+1)); echo ">> Rodada $r: $antes/$total feitas — reiniciando o modelo"
    reiniciar_e_esperar
    "${DC[@]}" exec -T ufpa_rag_ui python - <<PY
import signal, sys; from pathlib import Path
signal.signal(signal.SIGALRM, lambda *a: sys.exit(0)); signal.alarm($RODADA_S)
sys.path.insert(0, "scripts")
$codigo
PY
    limpar_parcial "$arq"
    agora=$(docker inspect -f '{{.State.StartedAt}}' ufpa_rag_llm)
    if [ "$agora" != "$INICIO" ]; then
      echo "!! Modelo reiniciou na rodada $r — descartando as linhas novas e refazendo"
      head -n "$antes" "$arq" > "$arq.tmp" && mv "$arq.tmp" "$arq"
    fi
    [ "$r" -ge 40 ] && { echo "RODADAS_DEMAIS"; exit 1; }
  done
}

echo ">> Geração (115 perguntas)"
etapa "$DADOS/$E2E" 115 "import testar_e2e_amostra as t
t.OUT_PATH = Path('tests/data/$E2E')
t.main()"

NRAG=$(grep -c '"rota": "rag_generico"' "$DADOS/$E2E" || true)
echo ">> Juiz ($NRAG respostas rag)"
etapa "$DADOS/$FID" "$NRAG" "import avaliar_fidelidade_llm as j
j.E2E_PATH = Path('tests/data/$E2E')
j.OUT_PATH = Path('tests/data/$FID')
j.main()"

echo ">> Julgamentos com falha: $(grep -c '"julgamento_falhou": true' "$DADOS/$FID" || true)"
echo ">> Respostas rag em <2 s (possível reserva): $(python3 -c "
import json;print(sum(1 for l in open('$DADOS/$E2E') if (d:=json.loads(l))['rota']=='rag_generico' and d['tempo_seg']<2))")"
cp "$DADOS/$E2E" "$DADOS/$FID" "$SAIDA/"
echo "=== Fim Fase B $(date -Is) ==="
