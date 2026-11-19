#!/usr/bin/env bash
# Instala o timer de usuário que roda vigiar_memoria_llm.sh a cada 2 minutos.
# Rodar uma vez:  ./scripts/instalar_vigia_memoria_llm.sh
# Ver execuções:  journalctl --user -u ufpa_rag_vigia_llm -n 20
# Desfazer:       systemctl --user disable --now ufpa_rag_vigia_llm.timer
set -euo pipefail
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/ufpa_rag_vigia_llm.service" <<UNIT
[Unit]
Description=Minerva - reinicia o ufpa_rag_llm quando a memória passa do limite

[Service]
Type=oneshot
ExecStart=/bin/bash $PROJ/scripts/vigiar_memoria_llm.sh
UNIT
cat > "$UNIT_DIR/ufpa_rag_vigia_llm.timer" <<UNIT
[Unit]
Description=Minerva - vigia a memória do ufpa_rag_llm a cada 2 minutos

[Timer]
OnBootSec=5min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now ufpa_rag_vigia_llm.timer
systemctl --user list-timers ufpa_rag_vigia_llm.timer --no-pager
