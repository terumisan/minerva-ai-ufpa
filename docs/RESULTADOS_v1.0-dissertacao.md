# Minerva — Resultados consolidados (v1.0-dissertacao)

22/11/2026 · cópia versionada do documento de resultados; números extraídos de `ROADMAP_ENGENHARIA_V7.md`, seções 26–32.

Na versão congelada para a dissertação, a Minerva dá resposta útil a 82% (70 de 85) das perguntas da amostra D115 que passam pela busca nos documentos e foram julgadas nas três rodadas finais, com fidelidade média de 0,968 às fontes. As 864 formas de pergunta do catálogo recuperam o documento e a página certos (100%).

## Versão avaliada

| Item | Identificação |
| --- | --- |
| Código | tag `v1.0-dissertacao`, commit `0d4471c23656766f36bbd25c19effe79431745a2` (repositório minerva-ai-ufpa) |
| Catálogo | `minerva_dataset.json` 1.11.0 — 262 entradas, 980 variações, 1.178 evidências paginadas; SHA-256 `274de5428ed87b01e875217e2fb6049555c0378231ed71ff57872d9026e50ef9` |
| Modelo de linguagem | `Qwen_Qwen3.5-4B-Q4_0.gguf` via llama.cpp (`--jinja --reasoning-budget 0`, contexto 8192, 8/12 threads); SHA-256 `3e977de32dfb9377ff827f210091cce5d3c05c7b0f0b9b0c8005df7c0677a49b` |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (fastembed), busca híbrida léxica + semântica com fusão RRF, 6 trechos |
| Corpus | 28 PDFs oficiais da UFPA/FCT indexados (inclui editais de monitoria PROEG 22/2025 e 03/2026) |
| Máquina | notebook com Intel i5-1245U, só CPU; modelo limitado a 6 GiB de memória |
| Avaliação de referência | Fase B de 20/11/2026 (`resultado_*_v7_qwen35_20261120.jsonl`) |

## Arquitetura avaliada (V7)

Cada pergunta passa por uma cascata: a primeira etapa que tem base para responder encerra o fluxo, e o modelo de linguagem só entra no fim.

1. **Barreira institucional** — recusa perguntas sobre outras instituições.
2. **Roteador de rotas fixas** — responde perguntas genéricas (página do TCC, contatos, direção); perguntas específicas seguem adiante.
3. **Catálogo contextual** — casamento exato com 262 perguntas e 980 variações; exibe os trechos cadastrados, sem modelo de linguagem (~1 s).
4. **Busca híbrida** — 6 trechos por fusão RRF de busca léxica e semântica no pgvector; sem evidência suficiente, responde "Não localizei".
5. **Pergunta normativa** — o modelo só escolhe os IDs dos trechos que sustentam a resposta; a Minerva exibe os excertos integrais, nunca prosa gerada.
6. **Pergunta não normativa** — o modelo redige até 180 palavras citando `[T:ID]`; a resposta é recusada se citar trecho inexistente, URL ausente dos trechos ou trecho sem relação léxica com a pergunta, e vira exibição dos trechos se vier sem citação.

## Fase A: comparação de modelos

Com o código e o corpus do snapshot original da dissertação, o Qwen3.5-4B teve a maior taxa de acerto (82,5%) e a maior fidelidade (0,930), com latência igual à do Qwen2.5-7B original. Só o modelo muda entre as colunas; em cada execução o próprio modelo é o juiz.

| Fase A (14/11/2026) | Qwen2.5-7B (original) | Gemma 4 E4B | Qwen3.5-4B |
| --- | --- | --- | --- |
| Perguntas no fluxo generativo | 62 | 57 | 57 |
| Corretas (juiz) | 49 (79,0%) | 38 (66,7%) | 47 (82,5%; Wilson 70,6–90,2%) |
| Parciais / erradas | – | 12 / 7 | 8 / 2 |
| Fidelidade média | 0,902 | 0,929 | 0,930 |
| Gabarito no contexto recuperado | 46/62 | 47/57 | 47/57 |
| Latência média / mediana | 89,2 / 88,1 s | 73,9 / 70,8 s | 89,0 / 85,0 s |

Nove perguntas mudaram de rota em relação à execução original, por isso o Qwen2.5 avaliou 62 e os demais 57; a causa não foi investigada. O Gemma foi descartado por menor acerto e por estourar a memória (6 e 9 GiB) sob carga contínua.

## Catálogo

O catálogo cresceu de 239 para 262 entradas entre 18 e 19/11, e todas as 864 formas de pergunta da versão 1.7.0 recuperaram o documento e a página cadastrados (mediana de 0,8 s, nenhuma resposta de reserva).

| Versão | Entradas | Origem do acréscimo |
| --- | --- | --- |
| 1.7.0 (18/11) | 239 | 21 entradas de páginas sem cobertura e 134 paráfrases coloquiais como variações |
| 1.8.0 / 1.9.0 (19/11) | 252 | 13 entradas do agente de ampliação, aprovadas manualmente |
| 1.10.0 (19/11) | 254 | 2 entradas e 6 variações para as falhas reais da Fase B |
| 1.11.0 (19/11) | 262 | 8 entradas de monitoria (editais PROEG 22/2025 e 03/2026) |

Nas verificações: 210/210 entradas em 17/11; 198/198 paráfrases e formas novas no reteste de 18/11; 864/864 formulações em 18/11; 37/39 formas das entradas do agente (as 2 falhas eram variações ambíguas, removidas) e 8/8 perguntas de monitoria em 19/11.

## Fase B: arquitetura V7 de ponta a ponta

Na versão final, 82% das perguntas comparáveis recebem resposta útil e só 2 de 56 respostas em texto estão erradas. Útil = resposta julgada correta ou excerto exibido que contém o gabarito (cobertura ≥ 0,75 das palavras de conteúdo, `reavaliar_excertos.py`), porque o juiz conta a exibição de excertos como abstenção. Base: as 85 perguntas julgadas nas três rodadas, sem as perguntas sobre o próprio arquivo (assinaturas, autoria).

| | 18/11 | 19/11 | 20/11 (final) |
| --- | --- | --- | --- |
| Úteis | 68 (80%) | 68 (80%) | 70 (82%) |
| Corretas em prosa / parciais / erradas | 48 / 4 / 2 | 48 / 4 / 3 | 50 / 4 / 2 |
| Excertos com o gabarito / sem | 20 / 7 | 20 / 6 | 20 / 6 |
| Abstenções reais | 4 | 4 | 3 |
| Fidelidade média | 0,971 | 0,940 | 0,968 |
| Tempo médio | 40,3 s | 33,9 s | 43,1 s |

Na rodada de 14/11, antes do ajuste das rotas, 79 perguntas iam para a busca e 36 para o roteador; desde 18/11 são 103–106 e 9. Na rodada final todas as 103 respostas foram julgadas, sem falha de infraestrutura.

## Análises de efeito

Três mudanças tiveram efeito medido; a lista é cronológica.

| Data | Mudança | Efeito medido |
| --- | --- | --- |
| 18/11 | Rotas genéricas deixam de responder perguntas específicas | +27 perguntas na busca (79 → 106) sem queda de acerto; fidelidade 0,942 → 0,971 |
| 19/11 | Trava de sustentação léxica do trecho citado | Barrou a resposta inventada sobre o questionário socioeconômico; nenhuma das 61 respostas corretas da Fase B seria bloqueada |
| 19/11 | URL aceita só se estiver no trecho recuperado | "Como aderir ao Cadastro Único" passou de "Não localizei" a resposta correta |
| 19–20/11 | Indexação e retirada da Cartilha de Monitoria 2021 | Com a Cartilha, fidelidade 0,940 e 1 resposta errada nova; sem ela, 0,968 e as 3 perguntas afetadas corretas |

O caso da Cartilha mostra que um documento novo pode degradar respostas de outros temas: o corpus precisa de curadoria, não só de acréscimo.

## Desempenho

A leitura do prompt consome 90% do tempo de resposta: em 12 perguntas medidas em 19/11 (`medir_tempos.py`), o total médio foi 33,9 s, dos quais 30,7 s de leitura (~1.350 tokens a ~44 tok/s), 2,7 s de geração (~18 tokens) e 0,5 s de busca. O cache de prefixo do llama.cpp só reaproveita 596 tokens com o Qwen3.5-4B, qualquer que seja a ordem do prompt, provavelmente pela arquitetura híbrida do modelo; reordenar o prompt não teve efeito. Respostas pelo catálogo levam ~1 s.

## Limitações

- Sem avaliação com usuários: o protótipo foi avaliado só de forma automática.
- O juiz é o próprio modelo de linguagem; a exibição de excertos exigiu uma régua léxica complementar.
- A amostra D115 tem 115 linhas para 93 perguntas distintas e inclui perguntas sobre o próprio arquivo, excluídas da comparação.
- Falhas de infraestrutura (reinício do modelo, execuções paralelas) exigiram tratamento manual em 18 e 19/11.
- Tempo de 34–43 s por resposta em CPU comum; a variação entre rodadas não foi investigada.
- O catálogo não tem aprovação institucional: as entradas são conferências técnicas contra os PDFs.

## Fontes dos dados

- `ROADMAP_ENGENHARIA_V7.md`, seções 26–32 (tag `v1.0-dissertacao`).
- Fase A: `app/tests/data/resultado_{e2e,fidelidade}_{qwen35,gemma4}_v6.jsonl`.
- Fase B: `app/tests/data/resultado_{e2e,fidelidade}_v7_qwen35_2026111{8,9}.jsonl` e `_20261120.jsonl`.
- Régua de utilidade: `scripts/replicacao/reavaliar_excertos.py`; tempos: `app/scripts/medir_tempos.py`.
- Procedimento de reprodução: `REPRODUCAO.md`, com o manifesto SHA-256 de modelo, catálogo e 28 PDFs (`scripts/replicacao/conferir_versao.sh`).
