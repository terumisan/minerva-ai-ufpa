#!/usr/bin/env bash
# Confere se modelo, catálogo e PDFs são exatamente os da versão avaliada
# (v1.0-dissertacao). Modelo e PDFs não são versionados no Git; este manifesto
# é a única garantia de que a reprodução usa os mesmos arquivos.
set -uo pipefail
cd "$(dirname "$0")/../.."
MANIFESTO=scripts/replicacao/MANIFESTO_v1.0-dissertacao.sha256
if ! sha256sum -c "$MANIFESTO" --quiet; then
  echo "FALHOU: os arquivos acima diferem da v1.0-dissertacao (ou estão faltando)"; exit 1
fi
echo "OK: os $(wc -l < "$MANIFESTO") arquivos conferem com a v1.0-dissertacao"
extras=$(comm -13 <(awk '{print $2}' "$MANIFESTO" | grep '^documentos/' | sort) <(ls documentos/*.pdf | sort))
[ -n "$extras" ] && { echo "ATENÇÃO: PDFs a mais em documentos/ (seriam indexados e mudam os resultados):"; echo "$extras"; exit 1; }
exit 0
