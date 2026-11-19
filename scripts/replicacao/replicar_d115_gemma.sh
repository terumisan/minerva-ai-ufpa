#!/usr/bin/env bash
# Replicação do D115/62 com Gemma 4 E4B, isolando o modelo (fase A), e
# avaliação do V7 atual com a mesma amostra (fase B).
#
# Fase A — protocolo da dissertação, trocando SÓ o arquivo do modelo:
#   geração  : código do commit ed7f6cc (testar_e2e_amostra.py, 24/07/2026)
#   juiz     : código do commit 7cf72c2 (avaliar_fidelidade_llm.py, 26/08/2026)
#   corpus   : os 13 PDFs do gabarito + calendário 2026 anterior (ManualSagitta corrompido, 0 trechos)
#   servidor : flags do llama.cpp de ed7f6cc (-c 8192, threads 8/12, parallel 1, mlock)
#   juiz     : o próprio modelo local (regra original), agora Gemma
# Fase B — sistema V7 atual (26 documentos, catálogo, código atual), mesma
#   amostra e mesmo juiz; registrada como avaliação separada.
#
# Uso:  bash ~/minerva-ai-ufpa/scripts/replicacao/replicar_d115_gemma.sh
# Log:  ~/Downloads/replicacao_d115_gemma.log
set -euo pipefail

REPO="$HOME/minerva-ai-ufpa"
BASE="$HOME/minerva-repl"
LOG="$HOME/Downloads/replicacao_d115_gemma.log"
SAIDA="$HOME/Downloads/replicacao_d115_gemma"
MODELO="gemma-4-E4B_q4_0-it.gguf"
COMMIT_GERACAO="ed7f6cc"
COMMIT_JUIZ="7cf72c2"
PDFS=(ManualAlunoSIGAA.pdf ManualDiscenteDrive.pdf Matricula_Estagio.pdf Matricula_Estagio_Anexo.pdf
      Matricula_TCC.pdf RegimentoGeral.pdf Regimento_FCT.pdf Regulamento_Graduacao.pdf
      Resolucao_Ativ_Complementares.pdf Resolucao_Estagio.pdf Resolucao_Intercambios.pdf
      Resolucao_PraticasEnsino.pdf Resolucao_TCC.pdf)

mkdir -p "$SAIDA"
exec > >(tee -a "$LOG") 2>&1
echo "=== Início $(date -Is) ==="

DC_REPL=(docker compose -p minerva_repl -f "$BASE/compose.yml")
DC_V7=(docker compose -f "$REPO/docker-compose.yml")

religar_v7() {
  echo ">> Religando o modelo do V7"
  "${DC_REPL[@]}" stop llm >/dev/null 2>&1 || true
  "${DC_V7[@]}" start ufpa_rag_llm || true
}

# ---------------------------------------------------------------- preparação
test -f "$REPO/models/$MODELO" || { echo "ERRO: modelo $MODELO não encontrado"; exit 1; }
git -C "$REPO" cat-file -e "$COMMIT_GERACAO^{commit}"
git -C "$REPO" cat-file -e "$COMMIT_JUIZ^{commit}"
mkdir -p "$BASE"
[ -d "$BASE/v6" ]   || git -C "$REPO" worktree add --detach "$BASE/v6" "$COMMIT_GERACAO"
[ -d "$BASE/juiz" ] || git -C "$REPO" worktree add --detach "$BASE/juiz" "$COMMIT_JUIZ"
echo "geração: $(git -C "$BASE/v6" rev-parse HEAD)"
echo "juiz   : $(git -C "$BASE/juiz" rev-parse HEAD)"

mkdir -p "$BASE/documentos_v6"
rm -f "$BASE/documentos_v6"/*.pdf
for f in "${PDFS[@]}"; do cp "$REPO/documentos/$f" "$BASE/documentos_v6/"; done
# 14º documento do snapshot: calendário 2026 na versão anterior à troca de 13/11/2026
# (9 trechos, sem perguntas no gabarito, mas concorre na busca). O ManualSagitta de julho
# estava corrompido e não gerava trechos, por isso não entra.
cp "$HOME/Downloads/CalendarioAcademico2026_anterior.pdf" "$BASE/documentos_v6/CalendarioAcademico2026.pdf"
( cd "$BASE/documentos_v6" && sha256sum *.pdf ) | tee "$SAIDA/sha256_corpus_v6.txt"
sha256sum "$REPO/models/$MODELO" | tee "$SAIDA/sha256_modelo.txt"

# resultados do Qwen gravados nos commits não podem ser reaproveitados
# (os scripts são resumíveis e pulariam tudo)
rm -f "$BASE/v6/app/tests/data/resultado_e2e_amostra.jsonl"
rm -f "$BASE/juiz/app/tests/data/resultado_e2e_amostra.jsonl" "$BASE/juiz/app/tests/data/resultado_fidelidade_llm.jsonl"

cat > "$BASE/compose.yml" <<YML
services:
  db:
    image: ankane/pgvector:latest
    environment: {POSTGRES_DB: ufpa_rag, POSTGRES_USER: admin, POSTGRES_PASSWORD: replicacao}
    volumes: [pgdata_repl:/var/lib/postgresql/data]
  llm:
    image: ghcr.io/ggml-org/llama.cpp:server
    command: ["-m", "/models/$MODELO", "--host", "0.0.0.0", "--port", "8002", "-c", "8192",
              "--threads", "8", "--threads-batch", "12", "--parallel", "1", "--mlock"]
    volumes: ["$REPO/models:/models:ro"]
    healthcheck: {test: ["CMD", "curl", "-f", "http://localhost:8002/health"], interval: 15s, timeout: 5s, retries: 40, start_period: 30s}
  v6:
    build: ./v6/app
    working_dir: /app
    command: ["sleep", "infinity"]
    environment: &amb {DB_HOST: db, DB_PORT: "5432", DB_NAME: ufpa_rag, DB_USER: admin, DB_PASSWORD: replicacao,
                       LLM_API_URL: "http://llm:8002/v1/chat/completions", PYTHONUNBUFFERED: "1"}
    volumes: ["./v6/app:/app", "./documentos_v6:/documentos:ro"]
    depends_on: [db, llm]
  juiz:
    build: ./juiz/app
    working_dir: /app
    command: ["sleep", "infinity"]
    environment: *amb
    volumes: ["./juiz/app:/app"]
    depends_on: [db, llm]
volumes:
  pgdata_repl:
YML

# ------------------------------------------------------------------ fase A
echo ">> Desligando o modelo do V7 durante a medição (sem concorrência de CPU/RAM)"
"${DC_V7[@]}" stop ufpa_rag_llm
trap religar_v7 EXIT

"${DC_REPL[@]}" up -d --build
echo ">> Aguardando o servidor do modelo"
for i in $(seq 1 120); do
  st=$(docker inspect -f '{{.State.Health.Status}}' "$("${DC_REPL[@]}" ps -q llm)" 2>/dev/null || echo "?")
  [ "$st" = "healthy" ] && break; sleep 5
done
[ "$st" = "healthy" ] || { echo "ERRO: servidor do modelo não ficou saudável"; exit 1; }

echo ">> Ingestão com o código de $COMMIT_GERACAO"
"${DC_REPL[@]}" exec -T v6 python scripts/ingestao.py

echo ">> Conferência do corpus (precisa reproduzir o snapshot)"
"${DC_REPL[@]}" exec -T v6 python - <<'PY' | tee "$SAIDA/conferencia_corpus.txt"
import json, sys
sys.path.insert(0, "scripts")
from ingestao import conectar_banco
import testar_e2e_amostra as t
conn = conectar_banco(); cur = conn.cursor()
cur.execute("SELECT count(*) FROM documentos_ufpa"); total = cur.fetchone()[0]
cur.execute("SELECT nome_arquivo, conteudo FROM documentos_ufpa"); trechos = {(a, c) for a, c in cur.fetchall()}
pergs = json.load(open("tests/data/eval_minerva_qa.json"))["perguntas"]
amostra = t._amostra_estratificada(pergs, t.TAMANHO_AMOSTRA)
achados = sum((p["arquivo_fonte"], p["trecho_fonte"]) in trechos for p in amostra)
todos = sum((p["arquivo_fonte"], p["trecho_fonte"]) in trechos for p in pergs)
print(f"trechos no banco: {total} (snapshot: 395)")
print(f"amostra: {len(amostra)} perguntas (esperado 115)")
print(f"trecho-gabarito idêntico no banco: amostra {achados}/{len(amostra)}; D720 {todos}/{len(pergs)}")
ok = total == 395 and len(amostra) == 115 and achados == len(amostra)
print("CORPUS_OK" if ok else "CORPUS_DIVERGENTE")
PY
grep -q CORPUS_OK "$SAIDA/conferencia_corpus.txt" || { echo "ERRO: o corpus não reproduz o snapshot; replicação interrompida"; exit 1; }

echo ">> Geração das 115 respostas (pode levar 1–2 h)"
"${DC_REPL[@]}" exec -T v6 python scripts/testar_e2e_amostra.py
cp "$BASE/v6/app/tests/data/resultado_e2e_amostra.jsonl" "$SAIDA/resultado_e2e_gemma4_v6.jsonl"

echo ">> Juiz com o código de $COMMIT_JUIZ (pode levar ~1 h)"
cp "$SAIDA/resultado_e2e_gemma4_v6.jsonl" "$BASE/juiz/app/tests/data/resultado_e2e_amostra.jsonl"
"${DC_REPL[@]}" exec -T juiz python scripts/avaliar_fidelidade_llm.py | tee "$SAIDA/resumo_juiz_v6.txt"
cp "$BASE/juiz/app/tests/data/resultado_fidelidade_llm.jsonl" "$SAIDA/resultado_fidelidade_gemma4_v6.jsonl"
"${DC_REPL[@]}" exec -T llm sh -c 'cat /proc/cpuinfo | grep "model name" | head -1' > "$SAIDA/hardware.txt" || true

"${DC_REPL[@]}" down
trap - EXIT
religar_v7

# ------------------------------------------------------------------ fase B
echo ">> Aguardando o modelo do V7"
for i in $(seq 1 120); do
  st=$(docker inspect -f '{{.State.Health.Status}}' ufpa_rag_llm 2>/dev/null || echo "?")
  [ "$st" = "healthy" ] && break; sleep 5
done
echo ">> Fase B: mesma amostra no sistema V7 atual"
"${DC_V7[@]}" exec -T ufpa_rag_ui python - <<'PY'
import sys; from pathlib import Path
sys.path.insert(0, "scripts")
import testar_e2e_amostra as t
t.OUT_PATH = Path("tests/data/resultado_e2e_v7_gemma4_20261114.jsonl")
t.main()
PY
"${DC_V7[@]}" exec -T ufpa_rag_ui python - <<'PY' | tee "$SAIDA/resumo_juiz_v7.txt"
import sys; from pathlib import Path
sys.path.insert(0, "scripts")
import avaliar_fidelidade_llm as j
j.E2E_PATH = Path("tests/data/resultado_e2e_v7_gemma4_20261114.jsonl")
j.OUT_PATH = Path("tests/data/resultado_fidelidade_v7_gemma4_20261114.jsonl")
j.main()
PY
cp "$REPO/app/tests/data/resultado_e2e_v7_gemma4_20261114.jsonl" "$REPO/app/tests/data/resultado_fidelidade_v7_gemma4_20261114.jsonl" "$SAIDA/"
cp "$SAIDA/resultado_e2e_gemma4_v6.jsonl" "$REPO/app/tests/data/resultado_e2e_amostra_gemma4_v6.jsonl"
cp "$SAIDA/resultado_fidelidade_gemma4_v6.jsonl" "$REPO/app/tests/data/resultado_fidelidade_gemma4_v6.jsonl"
echo "=== Fim $(date -Is) — resultados em $SAIDA ==="
