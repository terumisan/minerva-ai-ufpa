#!/usr/bin/env bash
# Baixa os documentos oficiais de monitoria da PROEG, confere o SHA-256 e indexa na Minerva.
set -euo pipefail
cd ~/minerva-ai-ufpa
baixa() { wget -q -O "documentos/$1" "$2"; echo "$3  documentos/$1" | sha256sum -c -; }
baixa Edital_Monitoria_PROEG_22_2025.pdf https://proeg.ufpa.br/images/Artigos/Editais/EditalMonitoria2026.pdf 33bde24978ae1e5f667c013581c9cad534f9a0e91a56e09a69c9b4dfb06c597f
baixa Edital_MonitoriaVoluntaria_PROEG_03_2026.pdf https://proeg.ufpa.br/images/Artigos/MonitoriaVoluntaria2026-1.pdf cb391c9d3fb1870522b799f192d4b29d8ff1afaf44631fcdac802b7a2abdce5a
wget -q -O documentos/Cartilha_Monitoria_PROEG_2021.pdf https://proeg.ufpa.br/images/Artigos/Academico/Guias-Manuais/cartilhamonitoria2021.pdf && echo "cartilha baixada"
docker compose --profile manutencao run --rm --build ufpa_rag_ingestao --fontes /app/fontes_documentais.json
