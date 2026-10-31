#!/usr/bin/env bash
# Backup diário do Postgres da Minerva (dump lógico via pg_dump).
#
# Guarda os dumps FORA do repositório git — contêm dados reais de alunos
# (perguntas do chat, respostas abertas do formulário de avaliação), nunca
# devem ser versionados nem sincronizados com o GitHub.
#
# Uso: ./scripts/backup_postgres.sh
# (chamado pelo timer systemd ufpa_rag_backup_postgres.timer, ver README)

set -euo pipefail

CONTAINER="ufpa_rag_db"
BACKUP_DIR="${HOME}/ufpa_rag_backups"
RETENCAO_DIAS=14

# Lê DB_NAME/DB_USER do .env do projeto (mesmos valores usados pelo
# docker-compose.yml) em vez de duplicar/hardcodar credenciais aqui.
ENV_FILE="$(dirname "$0")/../.env"
DB_NAME="ufpa_rag"
DB_USER="admin"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$ENV_FILE"
    set +a
    DB_NAME="${DB_NAME:-ufpa_rag}"
    DB_USER="${DB_USER:-admin}"
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/ufpa_rag_${TIMESTAMP}.sql.gz"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "ERRO: container ${CONTAINER} não está rodando — backup abortado." >&2
    exit 1
fi

# --clean: dump inclui DROP antes de CREATE, pra um restore não precisar
# de banco vazio de antemão. Pipe direto pro gzip, sem arquivo intermediário
# sem compressão no disco.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" --clean --if-exists "$DB_NAME" \
    | gzip > "$DEST"

chmod 600 "$DEST"

TAMANHO="$(du -h "$DEST" | cut -f1)"
echo "Backup criado: ${DEST} (${TAMANHO})"

# Rotação: mantém só os últimos RETENCAO_DIAS dias de dumps.
find "$BACKUP_DIR" -name 'ufpa_rag_*.sql.gz' -mtime "+${RETENCAO_DIAS}" -delete

echo "Backups atuais em ${BACKUP_DIR}:"
ls -lh "$BACKUP_DIR"/ufpa_rag_*.sql.gz 2>/dev/null | tail -5
