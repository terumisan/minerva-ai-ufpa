# Reprodução dos resultados da dissertação — Minerva v1.0-dissertacao

Este roteiro refaz, a partir do repositório, as avaliações citadas na dissertação: a varredura do
catálogo, a Fase B (arquitetura V7 de ponta a ponta) e a medição de tempos. Os números de
referência estão em `ROADMAP_ENGENHARIA_V7.md`, seções 26 a 32.

## 1. O que define a versão avaliada

| Item | Identificação |
|---|---|
| Código | tag `v1.0-dissertacao` (commit `0d4471c23656766f36bbd25c19effe79431745a2`) |
| Catálogo | `app/minerva_dataset.json` 1.11.0 — 262 entradas, 980 variações |
| Modelo | `models/Qwen_Qwen3.5-4B-Q4_0.gguf` (llama.cpp, `--jinja --reasoning-budget 0`) |
| Corpus | 28 PDFs em `documentos/` |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (fastembed, baixado na primeira execução) |

O modelo e os PDFs **não são versionados** (ver `.gitignore`). O arquivo
`scripts/replicacao/MANIFESTO_v1.0-dissertacao.sha256` registra o SHA-256 de cada um, do modelo e
do catálogo; `scripts/replicacao/conferir_versao.sh` confere tudo de uma vez. Um PDF a mais em
`documentos/` muda os resultados: em 19/11 a inclusão da Cartilha de Monitoria 2021 derrubou a
fidelidade de 0,971 para 0,940 (ROADMAP §32).

## 2. Requisitos

- Linux com Docker e Docker Compose.
- CPU x86-64; a avaliação de referência usou um Intel i5-1245U, sem GPU. Os tempos dependem da
  máquina; acertos e fidelidade não deveriam depender.
- 16 GB de RAM (o modelo roda limitado a 6 GiB) e ~10 GB livres em disco.
- Para a Fase B: ~3 horas de máquina dedicada.

## 3. Preparar o ambiente

```bash
git clone https://github.com/terumisan/minerva-ai-ufpa.git
cd minerva-ai-ufpa
git checkout v1.0-dissertacao

cp .env.example .env          # defina DB_PASSWORD
```

**Modelo.** Coloque em `models/` o GGUF `Qwen_Qwen3.5-4B-Q4_0.gguf` (quantização Q4_0 do
Qwen3.5-4B). O arquivo vem de fora do repositório; o que garante que é o mesmo é o SHA-256 do
manifesto.

**Documentos.** Coloque em `documentos/` os 28 PDFs listados no manifesto, com os mesmos nomes.
`app/fontes_documentais.json` traz o endereço oficial (`*.ufpa.br`) da maioria deles. Os editais de
monitoria podem ser baixados e conferidos com `scripts/baixar_monitoria.sh`. Um PDF republicado
pela UFPA com outro conteúdo terá outro SHA-256: nesse caso a reprodução usa um corpus diferente
do avaliado, e isso deve ser registrado.

**Conferência — obrigatória antes de seguir:**

```bash
bash scripts/replicacao/conferir_versao.sh
# esperado: "OK: os 30 arquivos conferem com a v1.0-dissertacao"
```

## 4. Subir o sistema e indexar

```bash
docker compose up -d --build
docker compose --profile manutencao run --rm --build ufpa_rag_ingestao --fontes /app/fontes_documentais.json
docker compose exec -T ufpa_rag_ui python scripts/sincronizar_qa.py
```

O último comando deve terminar com um JSON contendo `"minerva_perguntas_respostas": 262` e
`"minerva_qa_variacoes": 980`. A interface fica em http://localhost:8501.

Recomendado em execuções longas: o vigia de memória, que reinicia o modelo quando o
`llama-server` passa do limite (o servidor tem vazamento de memória sob carga contínua):

```bash
bash scripts/instalar_vigia_memoria_llm.sh
```

## 5. Testes automatizados

```bash
cd app && ../.venv/bin/pytest -q && cd ..
```

Testes de integração com o banco exigem `MINERVA_TEST_DSN`; sem ela, são pulados.

## 6. Fase B — arquitetura V7 de ponta a ponta (resultado principal)

Faz as 115 perguntas da amostra D115 (`app/tests/data/eval_minerva_qa.json`) ao sistema e depois
pede ao próprio modelo que julgue cada resposta. Roda em rodadas de 6 minutos, reiniciando o
modelo entre elas.

```bash
cd scripts/replicacao
pgrep -fa repetir_fase_b || echo "nenhum rodando"     # só UMA execução por vez
(TAG=reproducao RODADA_S=360 nohup bash repetir_fase_b.sh > /dev/null 2>&1 &)
LOG=~/Downloads/replicacao_fase_b_reproducao.log TAG=reproducao bash progresso_e2e.sh
```

- Duas execuções simultâneas reiniciam o modelo uma da outra e nenhuma avança.
- Não reinicie a interface durante a execução.
- Se o juiz não terminar todas as respostas: `TAG=reproducao bash juiz_pendentes.sh`.
- Respostas "Não localizei" em menos de 2 s logo após um reinício do modelo são falha de
  infraestrutura, não do sistema: `TAG=reproducao bash refazer_falhas_infra.sh` as remove e refaz.

Saídas: `app/tests/data/resultado_e2e_v7_reproducao.jsonl` e
`resultado_fidelidade_v7_reproducao.jsonl`.

**Régua de utilidade.** O juiz conta a exibição de excertos normativos como abstenção. A
reavaliação considera útil o excerto que contém o gabarito (cobertura ≥ 0,75 das palavras de
conteúdo) e separa as perguntas sobre o próprio arquivo:

```bash
cd app/tests/data
python3 ../../../scripts/replicacao/reavaliar_excertos.py resultado_e2e_v7_reproducao.jsonl resultado_fidelidade_v7_reproducao.jsonl
```

Referência (20/11/2026, 85 perguntas comparáveis): 70 úteis (82%), 50 corretas em texto e 2
erradas, fidelidade média 0,968. O juiz é um modelo de linguagem: diferenças de uma ou duas
perguntas entre execuções são esperadas.

## 7. Tempos por etapa

```bash
docker exec ufpa_rag_ui python scripts/medir_tempos.py 12
```

Referência (19/11/2026): 33,9 s por resposta, dos quais 30,7 s de leitura do prompt, 2,7 s de
geração e 0,5 s de busca. Respostas pelo catálogo levam ~1 s.

## 8. Fase A — comparação de modelos

A comparação entre Qwen2.5-7B, Gemma 4 E4B e Qwen3.5-4B usa o código e o corpus do snapshot
original da dissertação (commits `ed7f6cc` e `7cf72c2`, 13 PDFs e o Calendário 2026 anterior),
não a versão atual. Procedimento e resultados: ROADMAP §26 e `scripts/replicacao/replicar_d115.sh`
(`replicar_d115_gemma.sh` para o Gemma).

## 9. O que não está automatizado

- **Varredura do catálogo** (864/864 formulações, 18/11/2026): feita pela interface pública com
  um script no navegador, que não foi versionado. A conferência equivalente é perguntar cada
  pergunta e variação de `app/minerva_dataset.json` e verificar se o primeiro trecho exibido é o
  documento e a página de `contexto_documental`.
- **Aprovação institucional do catálogo**: as entradas são conferências técnicas contra os PDFs,
  não validação da coordenação (planilhas em `docs/revisao_catalogo_*.xlsx`).
