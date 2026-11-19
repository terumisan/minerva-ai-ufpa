#!/usr/bin/env bash
# Rodada completa de ponta a ponta (18/11/2026), com a arquitetura atual (V7)
# e o modelo atual (Qwen3.5-4B):
#   1. reinicia a interface para carregar o código novo;
#   2. roda a suíte de testes dentro do container (com PostgreSQL real);
#   3. espera o sinal de fim da varredura do catálogo no site, que o Claude
#      faz pelo navegador e sinaliza criando ~/Downloads/varredura_catalogo_ok.flag
#      (limite de 4 h; depois segue mesmo sem o sinal);
#   4. roda as 115 perguntas do D115 no V7 + juiz, em rodadas (repetir_fase_b.sh).
# Uso: nohup bash ~/minerva-ai-ufpa/scripts/replicacao/e2e_completo.sh >/dev/null 2>&1 &
set -uo pipefail
REPO="$HOME/minerva-ai-ufpa"
LOG="$HOME/Downloads/e2e_completo_20261118.log"
FLAG="$HOME/Downloads/varredura_catalogo_ok.flag"
DC=(docker compose -f "$REPO/docker-compose.yml")
exec > >(tee -a "$LOG") 2>&1
echo "=== Início $(date -Is) ==="
rm -f "$FLAG"

echo ">> 1. Reiniciando a interface"
"${DC[@]}" restart ufpa_rag_ui
sleep 20

echo ">> 2. Testes automatizados no container"
"${DC[@]}" exec -T ufpa_rag_ui python -m pytest -q tests 2>&1 | tail -25
echo ">> Testes: fim"

echo ">> 3. Aguardando a varredura do catálogo no site"
for i in $(seq 1 240); do [ -f "$FLAG" ] && break; sleep 60; done
[ -f "$FLAG" ] && echo ">> Varredura concluída" || echo ">> Sem sinal da varredura após 4 h; seguindo"

echo ">> 4. D115 no V7 + juiz (Qwen3.5-4B)"
TAG=qwen35_20261118 bash "$REPO/scripts/replicacao/repetir_fase_b.sh"
echo "=== Fim $(date -Is) ==="
