#!/usr/bin/env bash
# Barra de status do teste de ponta a ponta (Fase B: D115 no V7 + juiz)
D=~/minerva-ai-ufpa/app/tests/data
TAG=${TAG:-qwen35_20261118}
TOTAL=${TOTAL:-115}
LOG=~/Downloads/e2e_completo_20261118.log
T0=$(stat -c %Y "$LOG" 2>/dev/null || date +%s)
barra(){ local n=$1 t=$2 w=40; local f=$(( t>0 ? n*w/t : 0 )); printf '[%-*s] %3d/%d (%3d%%)' $w "$(printf '#%.0s' $(seq 1 $f) 2>/dev/null)" "$n" "$t" $(( t>0 ? n*100/t : 0 )); }
while true; do
  E=$(wc -l < "$D/resultado_e2e_v7_$TAG.jsonl" 2>/dev/null || echo 0)
  J=$(wc -l < "$D/resultado_fidelidade_v7_$TAG.jsonl" 2>/dev/null || echo 0)
  TJ=$(grep -c '"rota": "rag_generico"' "$D/resultado_e2e_v7_$TAG.jsonl" 2>/dev/null || echo 0)
  S=$(( $(date +%s) - T0 ))
  ETA="--"; [ "$E" -gt 0 ] && [ "$E" -lt "$TOTAL" ] && ETA=$(date -u -d @$(( S*(TOTAL-E)/E )) +%H:%M:%S)
  clear
  echo "MINERVA — teste de ponta a ponta  ($(date +%H:%M:%S))"
  echo "Etapa atual: $(grep -E '^>>' "$LOG" 2>/dev/null | tail -1)"
  printf 'Respostas  '; barra "$E" "$TOTAL"; echo
  printf 'Juiz       '; barra "$J" "$TJ"; echo
  echo "Decorrido: $(date -u -d @$S +%H:%M:%S)   ETA respostas: $ETA"
  echo "Memória LLM: $(docker stats --no-stream --format '{{.MemUsage}}' ufpa_rag_llm 2>/dev/null)"
  echo; tail -3 "$LOG" 2>/dev/null
  sleep 10
done
