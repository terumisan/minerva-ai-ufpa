# AGENTS.md — Minerva AI (ufpa_rag)

Contexto operacional do projeto, consolidado a partir do histórico de trabalho com Claude Code. Ler antes de sugerir mudanças em deploy, embeddings, LLM ou ingestão de documentos.

## Visão geral
Minerva AI é um app Streamlit (RAG) rodando em `localhost:8501`, com pipeline de ingestão de PDFs (`documentos/` → Postgres `documentos_ufpa`) e um LLM local via llama.cpp em container Docker (`ufpa_rag_llm`).

## Pasta principal — consolidação em 30/10/2026
- Trabalhar em `~/minerva-ai-ufpa`. `~/ufpa_rag` é um link simbólico para essa mesma pasta, não outro checkout.
- O `.venv` de desenvolvimento foi transferido para a pasta principal. O link antigo mantém os caminhos dos executáveis compatíveis.
- Docker usa os bind mounts da pasta principal e o volume `minerva-ai-ufpa_pgdata_rag`; preservar esse volume.
- Serviços systemd de backup/reinício usam a pasta principal. Histórico Git/stashes antigos, relatórios privados, configurações antigas e modelos alternativos estão em `~/ufpa_rag_backups/consolidacao_20261030/`, fora do repositório.

## Deploy / infraestrutura
- Exposto publicamente via **ngrok** (conta free, `srterumi1@gmail.com`), serviço systemd `ngrok-minerva.service`. URL fixa (dev-domain): `https://preschool-unsaid-doodle.ngrok-free.dev` — não muda em reconexão. `ngrok` instalado em `~/.local/bin/ngrok` (sem root).
- Antes era Cloudflare quick tunnel (`cloudflared-minerva.service`) — desativado (não deletado) porque a URL mudava a cada reconexão.
- **Sem autenticação** na frente do app. Mencionar isso se surgir discussão sobre expor algo mais sensível.
- Domínio ngrok não é escolhível (plano free); confirmar sempre em https://dashboard.ngrok.com/domains antes de assumir o nome.
- `loginctl enable-linger terumi` ativo — túnel sobrevive a reboot/logout.

## LLM (`ufpa_rag_llm`, llama.cpp)
- Modelo ativo conferido em 30/10/2026: `gemma-4-E4B_q4_0-it.gguf`. Qwen2.5-7B e Llama-3.2-3B foram preservados no arquivo da consolidação; comparações abaixo são históricas, não medições do modelo ativo.
- Comparação medida (`app/scripts/comparar_llms.py`): Qwen3-4B ~2x mais rápido isolado (12.7 vs 6.1 tok/s gen), qualidade comparável/melhor em nuances. Mas a reversão para Qwen2.5-7B foi pedida pelo usuário sem explicação — **não presumir que foi por qualidade/velocidade**; perguntar antes de re-recomendar a troca.
- Timing de pipeline completo é enganoso: contenção de CPU no host distorce comparações wall-clock entre modelos. Preferir benchmark isolado, back-to-back, na mesma sessão.
- **Vazamento de memória conhecido**: o container cresce RAM sem limite com uptime longo (observado 11.2GB vs ~5GB esperado) ou após rajadas de ~50+ chamadas sequenciais — pode derrubar o container (`Connection refused`/`503`). Mitigado por timer systemd `ufpa_rag_restart_llm.timer` (reinicia às 04:00 diariamente). Se lento: checar `docker stats ufpa_rag_llm` e `free -h`; `docker compose restart ufpa_rag_llm` resolve na hora.
- `--threads`/`--threads-batch` já ajustados (8/12) — mais threads pioram a fase de geração (memory-bandwidth-bound) nesta máquina (i5-1245U).
- Scripts de avaliação longos contra o LLM devem ser resumíveis (append-as-you-go em JSONL, skip de itens já processados) — ver `app/scripts/avaliar_fidelidade_llm.py`.

## Embeddings / RAG
- Modelo de embedding: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768d), trocado do MiniLM (384d) após ganho medido (hit@6 semântico 44.2%→63.5%).
- `multilingual-e5-large` (2.3GB) foi testado e teve melhor score, mas **rejeitado por risco de memória** — RAM total da máquina é só 14GB e já houve incidente de swap-thrashing com o LLM. Só revisitar se a situação de memória do LLM estiver estável/monitorada.
- `ingestao.py` faz `DROP COLUMN IF EXISTS embedding` + `ADD COLUMN` no reindex — mudança de dimensão de embedding não precisa de migração manual.

## Dados / ingestão
- Corpus conferido em 30/10/2026: 15 PDFs, 413 chunks com embeddings. Duplicata e arquivos vazios foram removidos anteriormente.
- `ManualSagitta.pdf` foi substituído pelo PDF oficial íntegro (12 páginas, edição de 2015); 18 trechos inseridos, preservando os 395 anteriores. Fonte: https://sagitta.ufpa.br/sagitta/documentos/manual_sagitta.pdf.
- Ingestão com lote padrão excedeu os limites de 2 e 4 GiB da UI. Nesta execução foram usados lotes de 8 em `passage_embed`; o código padrão ainda não foi ajustado. Não repetir a ingestão padrão supondo que o problema esteja resolvido.
- `ingestao.py` faz TRUNCATE + rebuild completo a cada execução — contagens de chunks podem mudar; não confiar em números antigos, reconferir com `SELECT nome_arquivo, count(*) FROM documentos_ufpa GROUP BY nome_arquivo`.

## Convenções de trabalho observadas
- Eval set principal: 720 perguntas geradas por LLM a partir dos chunks-fonte (hit-rate@1, hit@6 lexical/semântico/híbrido RRF).
- Scripts de comparação/avaliação ficam em `app/scripts/` (`comparar_embeddings.py`, `comparar_llms.py`, `avaliar_fidelidade_llm.py`, `testar_retrieval_configs.py`), resultados em `app/tests/data/*.jsonl`.
