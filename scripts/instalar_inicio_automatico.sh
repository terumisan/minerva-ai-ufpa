#!/usr/bin/env bash
# ======================================================================
# Minerva AI — instala o início automático no boot
#
# Rodar UMA vez:   ./scripts/instalar_inicio_automatico.sh
#
# O que faz:
#   1. Garante que o Docker inicia junto com o sistema (pede sudo só se precisar).
#   2. Cria o serviço systemd de usuário "minerva.service", que espera o
#      Docker ficar pronto e roda "docker compose up -d" na pasta do projeto.
#   3. Garante que o túnel ngrok (ngrok-minerva.service) também inicia.
#   4. Ativa o "linger", para tudo subir mesmo sem fazer login.
#
# Para desfazer:
#   systemctl --user disable --now minerva.service
#   rm ~/.config/systemd/user/minerva.service && systemctl --user daemon-reload
# ======================================================================
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER="$(command -v docker || true)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/minerva.service"

if [ -z "$DOCKER" ]; then
  echo "ERRO: comando 'docker' não encontrado." >&2
  exit 1
fi
if [ ! -f "$PROJ/docker-compose.yml" ]; then
  echo "ERRO: docker-compose.yml não encontrado em $PROJ" >&2
  exit 1
fi

echo "==> Pasta do projeto: $PROJ"

# 1. Docker no boot
if [ "$(systemctl is-enabled docker 2>/dev/null || true)" != "enabled" ]; then
  echo "==> Habilitando o Docker no boot (vai pedir sua senha)..."
  sudo systemctl enable --now docker
else
  echo "==> Docker já inicia no boot."
fi

# 2. Serviço da Minerva
mkdir -p "$UNIT_DIR"
cat > "$UNIT" <<EOF
[Unit]
Description=Minerva AI - sobe os containers (docker compose up -d)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJ
# Espera até 2 minutos o Docker ficar pronto depois do boot
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 60); do $DOCKER info >/dev/null 2>&1 && exit 0; sleep 2; done; echo "Docker nao respondeu" >&2; exit 1'
ExecStart=$DOCKER compose up -d
TimeoutStartSec=900

[Install]
WantedBy=default.target
EOF
echo "==> Serviço criado: $UNIT"

systemctl --user daemon-reload
systemctl --user enable minerva.service

# 3. Túnel ngrok
if [ -f "$UNIT_DIR/ngrok-minerva.service" ]; then
  systemctl --user enable ngrok-minerva.service
  echo "==> Túnel ngrok habilitado no boot."
else
  echo "AVISO: ngrok-minerva.service não existe — o link público não vai subir sozinho."
  echo "       Veja a seção 'Exposição pública' do README."
fi

# 4. Linger (sobe sem precisar fazer login)
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]; then
  loginctl enable-linger "$USER" || sudo loginctl enable-linger "$USER"
fi
echo "==> Linger ativo para $USER."

# Sobe agora, para testar
echo "==> Iniciando agora para testar..."
systemctl --user restart minerva.service
systemctl --user --no-pager status minerva.service | head -n 8 || true

echo
echo "Pronto! A Minerva vai subir sozinha sempre que o computador ligar."
echo "Local:   http://localhost:8501"
echo "Público: https://preschool-unsaid-doodle.ngrok-free.dev"
