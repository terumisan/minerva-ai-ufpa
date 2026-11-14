#!/usr/bin/env bash
# ======================================================================
# Minerva AI — roda LOCALMENTE e fica acessível por um LINK EXTERNO
#
# Rodar UMA vez:   ./scripts/instalar_inicio_automatico.sh
#
# Depois disso, sempre que o computador ligar:
#   - os containers da Minerva sobem neste computador (docker compose up -d)
#   - o túnel ngrok publica http://localhost:8501 num link externo fixo
#
# O que o script faz:
#   1. Garante que o Docker inicia junto com o sistema (pede sudo só se precisar).
#   2. Cria o serviço "minerva.service" (espera o Docker e sobe os containers).
#   3. Instala o ngrok se faltar, pede o authtoken se faltar e cria o serviço
#      "ngrok-minerva.service" com o domínio fixo.
#   4. Ativa o "linger", para tudo subir mesmo sem fazer login.
#   5. Sobe tudo agora e mostra o link externo.
#
# Outro domínio ngrok:  NGROK_URL=https://SEU-DOMINIO.ngrok-free.dev ./scripts/instalar_inicio_automatico.sh
# Senha no link (opcional; o padrão é sem senha):
#   MINERVA_LINK_SENHA='usuario:senha-com-8+caracteres' ./scripts/instalar_inicio_automatico.sh
#   Para tirar a senha, rode de novo sem a variável.
#
# Para desfazer:
#   systemctl --user disable --now minerva.service ngrok-minerva.service
# ======================================================================
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER="$(command -v docker || true)"
UNIT_DIR="$HOME/.config/systemd/user"
NGROK_URL="${NGROK_URL:-https://preschool-unsaid-doodle.ngrok-free.dev}"
NGROK="$(command -v ngrok || echo "$HOME/.local/bin/ngrok")"
SENHA="${MINERVA_LINK_SENHA:-}"

[ -n "$DOCKER" ] || { echo "ERRO: comando 'docker' não encontrado." >&2; exit 1; }
[ -f "$PROJ/docker-compose.yml" ] || { echo "ERRO: docker-compose.yml não encontrado em $PROJ" >&2; exit 1; }

echo "==> Pasta do projeto: $PROJ"
mkdir -p "$UNIT_DIR"

# ---------------------------------------------------------------- 1. Docker
if [ "$(systemctl is-enabled docker 2>/dev/null || true)" != "enabled" ]; then
  echo "==> Habilitando o Docker no boot (vai pedir sua senha)..."
  sudo systemctl enable --now docker
else
  echo "==> Docker já inicia no boot."
fi

# ------------------------------------------------------ 2. Serviço Minerva
cat > "$UNIT_DIR/minerva.service" <<EOF
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
echo "==> Serviço local criado: minerva.service"

# --------------------------------------------------- 3. Link externo (ngrok)
if [ ! -x "$NGROK" ]; then
  echo "==> Instalando o ngrok em ~/.local/bin ..."
  mkdir -p "$HOME/.local/bin"
  curl -sSL -o /tmp/ngrok.tgz "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
  tar -xzf /tmp/ngrok.tgz -C "$HOME/.local/bin" ngrok
  chmod +x "$HOME/.local/bin/ngrok"
  NGROK="$HOME/.local/bin/ngrok"
fi

if ! grep -qs "authtoken" "$HOME/.config/ngrok/ngrok.yml" "$HOME/.ngrok2/ngrok.yml"; then
  echo
  echo "O ngrok precisa do authtoken da sua conta."
  echo "Pegue em: https://dashboard.ngrok.com/get-started/your-authtoken"
  read -r -s -p "Cole o authtoken e aperte Enter: " TOKEN; echo
  "$NGROK" config add-authtoken "$TOKEN"
fi

AUTH_ARG=""
AUTH_ENV=""
if [ -n "$SENHA" ]; then
  case "$SENHA" in
    *:????????*) ;;
    *) echo "ERRO: MINERVA_LINK_SENHA deve ser 'usuario:senha' com senha de 8+ caracteres." >&2; exit 1 ;;
  esac
  # A senha fica num arquivo só do usuário, não dentro do serviço.
  install -m 600 /dev/null "$UNIT_DIR/ngrok-minerva.env"
  printf 'MINERVA_LINK_SENHA=%s\n' "$SENHA" > "$UNIT_DIR/ngrok-minerva.env"
  AUTH_ARG=' --basic-auth=${MINERVA_LINK_SENHA}'
  AUTH_ENV="EnvironmentFile=$UNIT_DIR/ngrok-minerva.env"
  echo "==> Link externo com senha (usuário: ${SENHA%%:*})."
else
  rm -f "$UNIT_DIR/ngrok-minerva.env"
  echo "==> Link externo sem senha (padrão)."
fi

cat > "$UNIT_DIR/ngrok-minerva.service" <<EOF
[Unit]
Description=ngrok - link externo da Minerva AI ($NGROK_URL)
After=network-online.target minerva.service
Wants=network-online.target minerva.service

[Service]
$AUTH_ENV
ExecStart=$NGROK http 8501 --url=$NGROK_URL --log=stdout$AUTH_ARG
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
echo "==> Serviço do link externo criado: ngrok-minerva.service"

# ----------------------------------------------------------------- 4. Linger
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)" != "yes" ]; then
  loginctl enable-linger "$USER" || sudo loginctl enable-linger "$USER"
fi
echo "==> Linger ativo para $USER (sobe sem precisar fazer login)."

# ------------------------------------------------------- 5. Ativar e testar
systemctl --user daemon-reload
systemctl --user enable minerva.service ngrok-minerva.service
echo "==> Subindo agora..."
systemctl --user restart minerva.service
systemctl --user restart ngrok-minerva.service

echo "==> Aguardando a Minerva responder em localhost:8501 (até 3 min)..."
OK_LOCAL=no
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8501/_stcore/health >/dev/null 2>&1; then OK_LOCAL=yes; break; fi
  sleep 2
done

TUNEL="$(curl -fsS http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"[^"]*"' | head -n1 | cut -d'"' -f4 || true)"

echo
echo "================ RESULTADO ================"
echo "Local (este computador): http://localhost:8501   -> $([ "$OK_LOCAL" = yes ] && echo OK || echo 'ainda subindo / verificar')"
echo "Link externo (outros):   ${TUNEL:-$NGROK_URL}   -> $([ -n "$TUNEL" ] && echo OK || echo 'verificar: journalctl --user -u ngrok-minerva -n 30')"
echo "==========================================="
echo "Quem abrir o link externo verá um aviso do ngrok: basta clicar em 'Visit Site'."
if [ -n "$SENHA" ]; then
  echo "O link pede usuário e senha (definidos em MINERVA_LINK_SENHA)."
fi
echo "A partir de agora, tudo isso sobe sozinho sempre que o computador ligar."
