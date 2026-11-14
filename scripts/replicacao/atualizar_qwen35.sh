#!/usr/bin/env bash
# Troca o modelo do Minerva para o Qwen3.5 4B (se for mais rápido que o Gemma 4
# E4B no mesmo hardware) e refaz a avaliação D115: fase A (código e corpus da
# dissertação, só o modelo trocado) e fase B (V7 atual, em rodadas).
# Uso: nohup bash ~/minerva-ai-ufpa/scripts/replicacao/atualizar_qwen35.sh >/dev/null 2>&1 &
set -euo pipefail
REPO="$HOME/minerva-ai-ufpa"
DIR="$REPO/scripts/replicacao"
LOG="$HOME/Downloads/atualizar_qwen35.log"
GEMMA="gemma-4-E4B_q4_0-it.gguf"
QWEN="Qwen_Qwen3.5-4B-Q4_0.gguf"
URL="https://huggingface.co/bartowski/Qwen_Qwen3.5-4B-GGUF/resolve/main/$QWEN"
IMG="ghcr.io/ggml-org/llama.cpp:server"
FLAGS=(--jinja --reasoning-budget 0)
DC=(docker compose -f "$REPO/docker-compose.yml")
exec > >(tee -a "$LOG") 2>&1
echo "=== Início $(date -Is) ==="

echo ">> 1. Baixando $QWEN (~2,8 GB)"
# a pasta models/ pertence ao root: baixa em Downloads e copia via contêiner
echo ">> 2. Atualizando a imagem do llama.cpp (arquitetura do Qwen3.5 exige versão recente)"
docker pull -q "$IMG"
if [ ! -f "$REPO/models/$QWEN" ]; then
  curl -fL -C - --retry 5 -o "$HOME/Downloads/$QWEN" "$URL"
  docker run --rm --entrypoint cp -v "$HOME/Downloads:/d:ro" -v "$REPO/models:/m" "$IMG" "/d/$QWEN" "/m/$QWEN"
  rm -f "$HOME/Downloads/$QWEN"
fi
sha256sum "$REPO/models/$QWEN"

echo ">> 3. Comparando velocidade (V7 parado durante o teste)"
"${DC[@]}" stop ufpa_rag_llm
trap '"${DC[@]}" start ufpa_rag_llm >/dev/null || true' EXIT
python3 - > /tmp/prompt_bench.json <<'PY'
import json
ctx = ("Art. 5º O estágio supervisionado obrigatório terá carga horária mínima definida no "
       "projeto pedagógico do curso e será acompanhado por docente orientador e supervisor "
       "da parte concedente, mediante termo de compromisso e plano de atividades. ") * 22
msg = [{"role":"system","content":"Responda em português do Brasil, só com base no contexto."},
       {"role":"user","content":f"Contexto:\n{ctx}\n\nPergunta: Quem acompanha o estágio e quais documentos são exigidos?"}]
print(json.dumps({"messages":msg,"max_tokens":150,"temperature":0}))
PY
medir() {  # $1 modelo -> imprime segundos médios de 2 execuções
  docker rm -f bench_llm >/dev/null 2>&1 || true
  docker run -d --name bench_llm -p 8099:8002 -v "$REPO/models:/models:ro" "$IMG" \
    -m "/models/$1" --host 0.0.0.0 --port 8002 -c 8192 --threads 8 --threads-batch 12 \
    --parallel 1 "${FLAGS[@]}" >/dev/null
  for i in $(seq 1 60); do curl -sf localhost:8099/health >/dev/null && break; sleep 3; done
  curl -sf localhost:8099/v1/chat/completions -H 'Content-Type: application/json' -d @/tmp/prompt_bench.json >/dev/null  # aquecimento
  local t0 t1 resp
  t0=$(date +%s%N)
  for i in 1 2; do
    resp=$(curl -sf localhost:8099/v1/chat/completions -H 'Content-Type: application/json' -d @/tmp/prompt_bench.json)
  done
  t1=$(date +%s%N)
  echo "$resp" | python3 -c "import json,sys;c=json.load(sys.stdin)['choices'][0]['message'];print('   resposta:',c['content'][:300].replace(chr(10),' '));print('   thinking vazio:', not c.get('reasoning_content') and '<think>' not in c['content'])" >&2
  docker rm -f bench_llm >/dev/null
  echo $(( (t1 - t0) / 2000000 ))  # ms por execução
}
TG=$(medir "$GEMMA"); echo "   Gemma 4 E4B: ${TG} ms"
TQ=$(medir "$QWEN");  echo "   Qwen3.5 4B : ${TQ} ms"
if [ "$TQ" -ge "$TG" ]; then
  echo "MANTER_GEMMA: o Qwen3.5 4B não foi mais rápido; nada foi trocado"; exit 0
fi
echo ">> Qwen3.5 4B mais rápido — trocando o modelo do V7"
trap - EXIT
# edita o .env via contêiner (o arquivo pode pertencer ao root)
docker run --rm --entrypoint sh -v "$REPO:/r" "$IMG" -c \
  "touch /r/.env; grep -q '^LLM_MODEL=' /r/.env && sed -i 's/^LLM_MODEL=.*/LLM_MODEL=$QWEN/' /r/.env || echo 'LLM_MODEL=$QWEN' >> /r/.env"
grep '^LLM_MODEL=' "$REPO/.env" || docker run --rm --entrypoint grep -v "$REPO:/r" "$IMG" '^LLM_MODEL=' /r/.env
"${DC[@]}" up -d ufpa_rag_llm
for i in $(seq 1 60); do curl -sf localhost:8002/health >/dev/null && break; sleep 3; done
"${DC[@]}" exec -T ufpa_rag_llm sh -c 'cat /proc/1/cmdline | tr "\0" " "'; echo

echo ">> 4. Fase A (protocolo da dissertação com Qwen3.5)"
MODELO="$QWEN" TAG=qwen35 FLAGS_MODELO=', "--jinja", "--reasoning-budget", "0"' bash "$DIR/replicar_d115.sh"
echo ">> 5. Fase B (V7 atual com Qwen3.5, em rodadas)"
TAG=qwen35 bash "$DIR/repetir_fase_b.sh"
echo "=== Fim $(date -Is) ==="
