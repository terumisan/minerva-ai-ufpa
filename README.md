# Minerva AI — FCT/UFPA

Assistente virtual acadêmica da **Faculdade de Computação e Telecomunicações (FCT)** da **Universidade Federal do Pará (UFPA)**. Responde perguntas institucionais (calendário, TCC, estágio, matrícula, regulamentos, cardápio do RU) com base em documentos oficiais, rodando 100% em infraestrutura própria — sem depender de nenhuma API de IA paga.

> M.I.N.E.R.V.A. — Módulo Inteligente de Navegação e Ensino de Recursos Virtuais Acadêmicos.

---

## Sumário

- [Visão geral](#visão-geral)
- [Estado atual e próxima etapa](#estado-atual-e-próxima-etapa)
- [Arquitetura](#arquitetura)
- [Como a Minerva responde uma pergunta](#como-a-minerva-responde-uma-pergunta)
- [Stack técnica](#stack-técnica)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Como rodar](#como-rodar)
- [Exposição pública (ngrok, domínio fixo)](#exposição-pública-ngrok-domínio-fixo)
- [Configuração](#configuração)
- [Ingestão de documentos](#ingestão-de-documentos)
- [Desenvolvimento](#desenvolvimento)
- [Segurança](#segurança)
- [Operação e infraestrutura](#operação-e-infraestrutura)
- [Limitações conhecidas](#limitações-conhecidas)

---

## Visão geral

A Minerva é um chatbot RAG (*Retrieval-Augmented Generation*) construído para alunos e servidores da FCT/UFPA. Em vez de depender de um provedor de LLM externo, ela combina:

- Um **modelo de linguagem local** (llama.cpp, rodando um modelo GGUF de poucos bilhões de parâmetros em CPU).
- Uma **base vetorial própria** (Postgres + pgvector) com os documentos oficiais da faculdade já indexados.
- Um **roteador de perguntas em camadas**, que responde direto (sem passar pelo LLM) perguntas frequentes e bem definidas — calendário, cardápio do RU, contatos, siglas institucionais — antes de cair no RAG genérico.
- **Barreiras de escopo institucional**: a Minerva se recusa a responder como se fosse outra universidade (proteção explícita contra confundir FCT/UFPA com instituições homônimas, tipo a "FCT" de Portugal).

Interface web em Streamlit, conversas múltiplas por sessão (estilo ChatGPT), exportação de histórico e download dos documentos originais (PDF) ou reformatados (DOCX).

## Estado atual e próxima etapa

A revalidação de 30/10/2026 aprovou 222 testes com PostgreSQL/pgvector,
Ruff, compilação, os fluxos de TCC e SAGITTA no navegador e a restauração de
backup em banco separado. A base continha 413 trechos de 15 documentos em 30/10/2026; em 13/11/2026
foram acrescentados 11 documentos (26 no total), cuja ingestão muda essa contagem. Os
resultados e seus limites estão no [roadmap](ROADMAP_ENGENHARIA_V7.md), seção 18.

Em 12/11/2026 o catálogo foi ampliado de 92 para 138 entradas (137 ativas),
cobrindo o Regulamento do Ensino de Graduação, orientação/avaliação/defesa da
Resolução FCT 01/2012 e os manuais do SAGITTA e do SIGAA. As 46 entradas novas
passaram pela validação do catálogo e pelos testes sem banco, mas não foram
avaliadas quanto à qualidade das respostas; ver roadmap, seção 20.

Essas verificações dão suporte a uma rodada controlada de avaliação. Ainda
é necessário verificar se as respostas são corretas, completas, pertinentes
ao curso e sustentadas por fontes vigentes. Recuperar o documento certo e
validar a referência são partes dessa avaliação. A V7 permanece sem
homologação técnica e institucional integral.

A próxima etapa proposta é revisar de 20 a 30 perguntas importantes, com
formulações diferentes das usadas no desenvolvimento, antes de ampliar o
catálogo ou trocar modelos. O [plano de avaliação controlada](docs/AVALIACAO_CONTROLADA_V7.md)
define amostra, rubrica, registro de erros, medição de latência e critérios
para decidir os próximos ajustes.

## Arquitetura

```
┌─────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│   Navegador      │◄────►│  ufpa_rag_ui          │◄────►│  ufpa_rag_db        │
│  (Streamlit UI)  │      │  Streamlit + Python   │      │  Postgres + pgvector│
└─────────────────┘      │  (app/*.py)           │      │  (histórico +       │
                          │                        │      │   documentos_ufpa) │
                          └──────────┬─────────────┘      └────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  ufpa_rag_llm         │
                          │  llama.cpp server     │
                          │  (modelo GGUF local)  │
                          └──────────────────────┘
```

Três serviços principais e um worker opcional no `docker-compose.yml`:

| Serviço | Imagem | Função |
|---|---|---|
| `ufpa_rag_ui` | build local (`app/Dockerfile`) | App Streamlit — toda a lógica da Minerva |
| `ufpa_rag_db` | `ankane/pgvector` | Postgres com a extensão `pgvector` — histórico de conversas + chunks de documentos com embeddings |
| `ufpa_rag_llm` | `ghcr.io/ggml-org/llama.cpp:server` | Serve o modelo GGUF local via API compatível com `/v1/chat/completions` |
| `ufpa_rag_ingestao` | build local (`app/Dockerfile`), perfil `manutencao` | Processa PDFs em execução separada da UI, com limite próprio de memória |

## Como a Minerva responde uma pergunta

1. **Entrada e capacidade:** `operacao.py` valida a pergunta e controla o atendimento. Há limite de 4.000 caracteres, intervalo mínimo por sessão e uma consulta por processo da UI, sem fila de espera.
2. **Contexto específico:** `minerva_dataset.py` reconhece perguntas e variações explícitas do catálogo. Saudações e cortesias nas pontas da frase ("Minerva,", "oi", "por favor", "obrigado") são ignoradas quando a frase inteira não casa; o restante precisa ser idêntico a um alias. O JSON do catálogo é relido só quando o arquivo muda. Quando há correspondência única com contexto documental, a consulta segue para o RAG com restrição de documento, versão e páginas, evitando respostas temáticas mais amplas.
3. **Roteamento das demais perguntas:** `minerva_priority_router.py` combina fatos básicos, dataset e rotas temáticas. Algumas rotas consultam páginas oficiais da UFPA com validação de domínio, redirecionamento e endereço de destino. Resposta literal do dataset exige manifesto aprovado, hashes, revisor e validade; na ausência dessa aprovação, a entrada não libera texto fixo.
4. **Recuperação documental:** `minerva_hybrid.py` combina busca lexical e semântica por RRF. Para um alias exato cujo formulário curto não atinja correspondência suficiente, pode recuperar as páginas cadastradas, conferindo o hash do documento. Isso não reduz o limiar semântico global.
5. **Resposta e referências:** pergunta do catálogo (passo 2) não chama o LLM: os trechos são escolhidos pela ordem da busca restrita às páginas cadastradas (até 3, mais ressalvas do mesmo documento), com as mesmas barreiras de abandono e nível de ensino (`resposta_contextual`). No modo normativo conservador, o LLM seleciona IDs (com `max_tokens` 64, pois só devolve JSON) e a aplicação transcreve os excertos com ressalvas. Nas demais consultas RAG, a geração precisa usar referências válidas do contexto. A aplicação aguarda a validação antes de exibir o texto; evidência insuficiente ou referência inválida pode produzir abstenção.

As barreiras institucionais e de referências reduzem falhas específicas da
geração. Elas não demonstram que toda afirmação está sustentada ou que uma
norma permanece vigente. A revisão editorial das rotas fixas e de
`minerva_basic_facts.py` também continua pendente.

6. **Cache de repetição:** `minerva_cache.py` guarda em memória (256 itens, 12 h; `MINERVA_CACHE_CAPACIDADE`, `MINERVA_CACHE_TTL`) respostas documentais bem-sucedidas, pela pergunta normalizada. A chave inclui o `minerva_dataset.json` e o manifesto do corpus, então mudar o catálogo ou os PDFs invalida tudo. Fallbacks e degradações nunca são guardados. A rota registrada no histórico é `rag_cache`.

## Stack técnica

- **Python 3.10**
- **Streamlit 1.59** — interface web
- **PostgreSQL + pgvector** — histórico de conversas e busca vetorial
- **llama.cpp** — inferência local em CPU; modelo ativo conferido em 30/10/2026: `gemma-4-E4B_q4_0-it.gguf`. Comparações anteriores com Qwen/Llama são históricas.
- **fastembed** — embeddings (`paraphrase-multilingual-mpnet-base-v2`, 768d, ONNX, sem depender de GPU/torch — trocado do MiniLM-L12 384d após medir com `app/scripts/comparar_embeddings.py`: hit-rate@6 semântico saltou de 44,2% para 63,5% na base real. O `multilingual-e5-large` media ainda melhor, mas 2,3GB era arriscado demais de memória nesta máquina)
- **langchain-text-splitters** + **pypdf** — extração e *chunking* dos PDFs institucionais na ingestão
- **python-docx** — geração de documentos `.docx` a partir do conteúdo indexado
- **uv** (Astral) — instalador de dependências (Dockerfile e CI)
- **pytest** + **ruff** — testes e lint
- **GitHub Actions** — Ruff e pytest com PostgreSQL/pgvector em push/PR para `main` e `melhorias/roadmap-engenharia`.

## Estrutura do projeto

```
minerva-ai-ufpa/
├── docker-compose.yml          # serviços principais e worker opcional
├── .env.example                # template de credenciais (copiar pra .env)
├── documentos/                 # PDFs oficiais fonte (não versionados)
├── models/                     # modelos .gguf locais (não versionados)
├── pyproject.toml              # config do ruff + pytest
├── scripts/                    # operação do host: backup, validação de backup, início automático
├── .github/workflows/ci.yml    # CI
└── app/
    ├── main.py                 # orquestrador: session state, sidebar, fluxo do chat
    ├── config.py                # credenciais/URLs (st.secrets > env var > default) + logging
    ├── db.py                    # pool de conexões, histórico de conversas (Postgres)
    ├── documents.py              # localização de PDFs, geração de DOCX, busca por intenção
    ├── prompts.py                # prompt institucional, barreiras pré/pós-geração, chamada ao LLM
    ├── ui.py                     # CSS, sidebar (conversas/categorias), renderização do chat
    ├── minerva_history.py        # normalização de histórico (funções puras, testadas)
    ├── minerva_hybrid.py          # busca híbrida (léxica + semântica) e fusão RRF
    ├── minerva_priority_router.py # roteador de rotas fixas + scraping controlado (*.ufpa.br)
    ├── minerva_basic_facts.py     # respostas sobre siglas/identidade institucional
    ├── minerva_dataset.py         # respostas cadastradas manualmente (minerva_dataset.json)
    ├── minerva_dataset.json       # perguntas, respostas candidatas, contextos e variações
    ├── minerva_qa_catalogo.py      # validação e publicação do catálogo no PostgreSQL
    ├── minerva_cache.py           # cache em memória de respostas RAG repetidas
    ├── minerva_static.py          # verificação da aprovação das respostas literais
    ├── operacao.py                # identidade anônima, entrada e limite de capacidade
    ├── web_segura.py              # acesso HTTPS oficial e validação de destino
    ├── scripts/ingestao.py        # extrai PDFs de documentos/, gera embeddings, popula o Postgres
    ├── scripts/sincronizar_qa.py  # valida PDFs/páginas e publica o catálogo no PostgreSQL
    ├── scripts/atualizar_evidencias_ampliacao.py # recalcula páginas das entradas de ampliação
    ├── tests/                     # suíte pytest e integração PostgreSQL/pgvector
    ├── requirements.txt            # dependências de produção (pinadas)
    ├── requirements-dev.txt        # + pytest/ruff, só pra dev/CI
    └── Dockerfile
```

## Como rodar

**Pré-requisitos**: Docker + Docker Compose. O modelo indicado no `command` de `ufpa_rag_llm` deve existir em `models/` (atualmente `gemma-4-E4B_q4_0-it.gguf`). PDFs institucionais em `documentos/`.

```bash
# 1. Credenciais do Postgres
cp .env.example .env
# edite .env e defina DB_PASSWORD

# 2. Suba os containers
docker compose up -d --build

# 3. Popule a base vetorial em um worker separado
docker compose --profile manutencao run --rm --build ufpa_rag_ingestao --fontes /app/fontes_documentais.json

# 4. Com os PDFs correspondentes ao dataset, publique o catálogo QA
docker compose exec -T ufpa_rag_ui python scripts/sincronizar_qa.py

# 5. Acesse
# http://localhost:8501
```

O Postgres fica acessível localmente em `127.0.0.1:5432` (não exposto pra fora da máquina) — útil pra inspecionar com `psql`/pgAdmin durante o desenvolvimento.

## Exposição pública (ngrok, domínio fixo)

Opcional: pra acessar a Minerva de outros dispositivos pela internet, sem ter domínio próprio nem abrir portas no roteador, o app é exposto via **ngrok** (conta gratuita, domínio "dev domain" fixo — não muda entre reinícios), rodando como serviço systemd de usuário.

Histórico: antes era exposto via Cloudflare quick tunnel, trocado por ngrok porque a URL do quick tunnel mudava toda vez que o túnel reconectava. Named tunnel da Cloudflare (URL fixa) exigiria domínio próprio numa conta Cloudflare, que não estava disponível.

```bash
# 1. Instala o binário do ngrok (sem root)
mkdir -p ~/.local/bin
curl -sSL -o /tmp/ngrok.tgz "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
tar -xzf /tmp/ngrok.tgz -C ~/.local/bin ngrok
chmod +x ~/.local/bin/ngrok

# 2. Configura o authtoken da conta (pegar em https://dashboard.ngrok.com/get-started/your-authtoken)
~/.local/bin/ngrok config add-authtoken <SEU_AUTHTOKEN>

# 3. O "dev domain" gratuito e fixo já vem atribuído à conta automaticamente
#    (nome gerado pelo ngrok, não escolhido pelo usuário — ver
#    https://dashboard.ngrok.com/domains). Nomes customizados (ex.: "minerva.ngrok-free.app")
#    exigem plano pago (ERR_NGROK_313) — usar exatamente o domínio listado no dashboard.

# 4. Cria o serviço systemd de usuário
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ngrok-minerva.service <<'EOF'
[Unit]
Description=ngrok Tunnel - Minerva AI (dominio fixo gratuito)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%h/.local/bin/ngrok http 8501 --url=https://<SEU_DEV_DOMAIN>.ngrok-free.dev --log=stdout
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# 5. Ativa o serviço e garante que sobrevive a logout/reboot
systemctl --user daemon-reload
systemctl --user enable --now ngrok-minerva.service
loginctl enable-linger $USER
```

URL pública atual: `https://preschool-unsaid-doodle.ngrok-free.dev` (fixa — não muda entre reinícios do serviço, ao contrário do quick tunnel).

⚠️ Sem autenticação na frente do app (mesma limitação de antes) — qualquer pessoa com o link acessa a Minerva.

### Início automático no boot (local + link externo)

Para a Minerva subir sozinha quando o computador ligar, rodando localmente e
acessível pelo link externo, execute **uma vez**:

```bash
./scripts/instalar_inicio_automatico.sh
```

O script habilita o Docker no boot (pede `sudo` só se necessário), cria
`~/.config/systemd/user/minerva.service` (espera o Docker e roda
`docker compose up -d` na pasta do projeto), instala o ngrok e pede o authtoken
se faltarem, recria `ngrok-minerva.service` para subir depois da Minerva, ativa
o linger e, ao final, mostra o estado local e o link externo. Outro domínio:
`NGROK_URL=https://SEU-DOMINIO.ngrok-free.dev ./scripts/instalar_inicio_automatico.sh`.

Verificação após reiniciar:

```bash
systemctl --user status minerva.service ngrok-minerva.service --no-pager
docker compose ps
journalctl --user -u minerva.service -b --no-pager | tail -30   # se não subir
```

Senha no link (opcional; padrão sem senha): `MINERVA_LINK_SENHA='usuario:senha-de-8+' ./scripts/instalar_inicio_automatico.sh`.
O script guarda a senha em `~/.config/systemd/user/ngrok-minerva.env` (permissão 600) e passa
`--basic-auth` ao ngrok; rodar de novo sem a variável remove a senha. Confirme no painel do ngrok se o seu
plano aceita basic auth.

Monitor: uma tarefa agendada no claude.ai ("Monitor Minerva", diária às 7h44 de Belém) abre o link e
avisa por notificação se ele estiver fora do ar, com o comando para religar.

Desfazer: `systemctl --user disable --now minerva.service ngrok-minerva.service`.
O link externo só funciona com o computador ligado e online; o plano gratuito do
ngrok mostra uma página de aviso na primeira visita ("Visit Site").

## Configuração

Tudo lido via `app/config.py::get_config()`, na ordem: `.streamlit/secrets.toml` → variável de ambiente → valor padrão.

| Variável | Padrão | Descrição |
|---|---|---|
| `DB_HOST` | `ufpa_rag_db` | Host do Postgres |
| `DB_PORT` | `5432` | Porta do Postgres |
| `DB_NAME` | `ufpa_rag` | Nome do banco |
| `DB_USER` | `admin` | Usuário do banco |
| `DB_PASSWORD` | — | Senha do banco (obrigatória, sem default) |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `10` | Tamanho do pool de conexões |
| `LLM_API_URL` | `http://ufpa_rag_llm:8002/v1/chat/completions` | Endpoint do llama.cpp |
| `DOCUMENTOS_DIR` | `documentos` | Onde procurar os PDFs originais pro download |
| `UFPA_LOGO_URL` | `app/assets/logo-ufpa.png` | Logo usado no favicon/cabeçalho |

## Ingestão de documentos

`app/scripts/ingestao.py`:

1. Lê todos os `.pdf` de `documentos/`.
2. Extrai o texto preservando marcadores estruturais (Art., Capítulo, Seção, §) como fronteiras de corte.
3. Fatia em chunks (~900 caracteres, overlap de 150) com `RecursiveCharacterTextSplitter`.
4. Gera embeddings em lotes de até 8, com o modelo/dimensão da busca; registra hash do PDF, hash/ID estável do trecho, páginas físicas e origem quando confirmada. Textos idênticos preservam o ID numérico.

Rodar (dentro do container, ou localmente com as mesmas env vars do `.env`):

```bash
docker compose exec -T ufpa_rag_ui python scripts/ingestao.py --fontes /app/fontes_documentais.json
```

A ingestão agora é incremental e atômica: PDFs inalterados são ignorados; mudanças são preparadas em staging temporário e publicadas em uma transação. Falhas de extração, vetor ou SQL preservam a base ativa. Não há `DROP` vetorial nem `TRUNCATE`; arquivos ausentes não são excluídos automaticamente. Dimensão incompatível é rejeitada. A primeira execução no legado calcula os metadados; execuções seguintes pulam arquivos inalterados.

Com o chat em uso, prefira o worker isolado para não carregar dois modelos no
mesmo limite de memória da UI:

```bash
docker compose --profile manutencao run --rm --build ufpa_rag_ingestao --fontes /app/fontes_documentais.json
```

O worker tem limite próprio de 2 GiB e 2 CPUs; `--batch-size` aceita 1 a 8.
`--force` reprocessa arquivos inalterados. `--fontes` recebe um JSON de nome
do PDF para URL HTTPS oficial; não invente origens desconhecidas. As páginas
são físicas do PDF e podem diferir da numeração impressa. Não há arquivo
completo de versões históricas dos PDFs nem revisão imutável do ONNX.

**Consistência dos dados-fonte** (`documentos/`, 15 PDFs válidos):
- `Regimento_UFPA_FCT.pdf` era um duplicado exato (MD5 idêntico) de `RegimentoGeral.pdf` — removido; mantido só `RegimentoGeral.pdf` (é o nome referenciado em `app/documents.py`, usado no download por palavra-chave). A duplicata inflava a base em ~33% de chunks repetidos e prejudicava o ranking do RRF (chunks idênticos competindo entre si) — hit-rate@1 subiu de 42,6% para 52,9% só com essa remoção.
- `Apresentacao_Eng_Computacao.pdf` e `Apresentacao_Eng_Telecomunicacoes.pdf` (0 bytes, vazios) — removidos.
- `ManualSagitta.pdf` foi substituído pelo PDF oficial íntegro: 12 páginas, edição de 2015 e 18 trechos. Corpus conferido em 30/10/2026: 413 trechos de 15 documentos.

## Desenvolvimento

### Catálogo de perguntas, contextos e variações

`app/minerva_dataset.json` é a fonte versionada do catálogo. A revisão
documental das 75 entradas literais acrescentou contexto, dispositivo,
páginas físicas, hash do PDF e evidências textuais; 40 respostas foram
corrigidas ou tiveram condições explicitadas. Há 12 ramificações novas,
195 variações nas entradas contextualizadas e relações tipadas entre assuntos.
Uma intenção duplicada foi inativada, preservando o registro anterior.

A ampliação de 12/11/2026 (versão 1.3.0, `MINERVA_0093` a `MINERVA_0138`)
acrescentou 46 entradas redigidas a partir de páginas dos PDFs locais:
Regulamento do Ensino de Graduação (28), Resolução FCT 01/2012 páginas 3–6 (9),
Manual SAGITTA (4), Manual SIGAA (2) e Resoluções EngComp de intercâmbio e
práticas de ensino (3). Cada uma tem duas variações, relações com o mesmo tema
e `origem_entrada.tipo = "ampliacao_documental"`. Temas já respondidos por
rotas fixas (trancamento, aproveitamento, segunda chamada, revisão de conceito,
composição de banca de TCC, "o que é SAGITTA") não receberam aliases, para não
trocar respostas instantâneas por geração.

Ampliação de 13/11/2026 (versão 1.4.0, `MINERVA_0139` a `MINERVA_0167`): 29 entradas a partir de 11
documentos novos colocados em `documentos/` — Resoluções CONSEPE 5.799/2024 (RADIP-EG), 5.824/2024
e 5.791/2024 (outorga de grau); Instruções Normativas PROEG 05/2023 (Trabalho de Curso), 04/2023
(reintegração), 01/2025 (tutoria, válida até o fim do calendário de 2026) e 02/2025 (prescrição); e
quatro guias da FCT publicados no Google Docs (TCC, estágio, atividades complementares, extensão).
Os guias de TCC e de estágio só existem como página publicada; os PDFs são transcrições do texto,
identificadas no cabeçalho. O calendário acadêmico de 2026 foi trocado pela versão atualizada da
PROEG (julho/2026). Os SHA-256 dos PDFs foram conferidos contra os sites na captura. A IN PROEG
01/2024 (tutoria) não foi incluída por ter expirado em 31/12/2024.

Divergência a confirmar com a Faculdade: o guia de estágio cita componentes de 120 h e 240 h
(360 h), enquanto a Resolução EngComp 02/2006 do corpus cita 200 h e 390 h.

Total: 167 entradas, 164 ativas; 162 contextualizadas, sendo 159 ativas.

Depois de colocar PDFs novos em `documentos/`, vetorize e publique nesta ordem:

```bash
docker compose --profile manutencao run --rm --build ufpa_rag_ingestao --fontes /app/fontes_documentais.json
docker compose exec -T ufpa_rag_ui python scripts/atualizar_evidencias_ampliacao.py
docker compose exec -T ufpa_rag_ui python scripts/sincronizar_qa.py
docker compose restart ufpa_rag_ui
```

Verificação de vigência (13/11/2026, versão 1.3.1): o Regulamento da Graduação (4.399/2013) segue
citado como vigente, mas foi complementado pelas Resoluções CONSEPE 5.799/2024 (RADIP-EG, regime
acadêmico diferenciado, vigente desde 2025.2), 5.791/2024 (outorga de grau) e 5.467/2022 (extensão).
`MINERVA_0104` e `MINERVA_0105` (exercício domiciliar) foram inativadas até a ingestão da 5.799/2024;
as demais complementações estão registradas em `curadoria_contextual.verificacao_vigencia_20261113`.
As resoluções da FCT (TCC 2012, estágio 2006, AC 2013, práticas 2008) seguem publicadas no site da
FCT e nenhuma substituta foi localizada. Para ingerir as resoluções de 2024 (URLs já em
`fontes_documentais.json`), baixe os PDFs para `documentos/` com os nomes
`Resolucao_RADIP_5799_2024.pdf` e `Resolucao_OutorgaGrau_5791_2024.pdf` e rode a ingestão.

Revisão pela coordenação: `docs/revisao_catalogo_20261113.xlsx` traz uma linha por entrada
(pergunta, variações, resposta proposta, texto das páginas, situação da norma) e colunas para
decisão (Aprovar/Corrigir/Recusar/Pendente), resposta corrigida, revisor e data.

Variações são formulações da mesma pergunta. Ramificações são perguntas
diferentes sobre condições, exceções, limites ou etapas relacionadas. Não
transforme uma ramificação em alias de uma resposta mais ampla. Perguntas
vagas sobre “o item VIII” ou “o conselho” ficam no registro anterior para
auditoria e não ganham contexto implícito por palavras-chave.

Publicação do catálogo no banco, depois da ingestão dos PDFs:

```bash
# só quando houver entradas de ampliação com evidências redigidas fora do container
docker compose exec -T ufpa_rag_ui python scripts/atualizar_evidencias_ampliacao.py
docker compose exec -T ufpa_rag_ui python scripts/sincronizar_qa.py
```

Perguntas simuladas (93, no estilo de alunos; não são de usuários reais) ficam em
`app/tests/data/perguntas_simuladas_20261113.json`. Para rodá-las no fluxo real e medir caminho, tempo,
documento/página citados e recusas (retomável; ~1 h com o modelo em CPU):

```bash
docker compose exec -T ufpa_rag_ui python scripts/avaliar_simuladas.py
```

O resultado vai para `tests/data/resultado_simuladas.jsonl` e `tests/data/resumo_simuladas.json`, que
lista falhas e sugere novas variações para o catálogo (perguntas que o RAG acertou devagar).

`atualizar_evidencias_ampliacao.py` recalcula, com o pypdf do container, o
texto e o hash das páginas citadas apenas nas entradas de ampliação; aborta se
o PDF não for o mesmo usado na redação e não altera perguntas, respostas nem
autorizações. É idempotente.

O comando confere hashes e texto das páginas locais, valida aliases/relações
e publica em uma transação: `minerva_perguntas_respostas`,
`minerva_qa_variacoes`, `minerva_qa_relacoes`, `minerva_qa_evidencias` e
`minerva_qa_versoes`. As evidências são vínculos de contexto por página, não
aprovação automática da resposta. Versão divergente do corpus aborta a
publicação. Perguntas e respostas não são inseridas como documentos factuais
na tabela vetorial; os 413 trechos dos PDFs permanecem separados.

Uma pergunta/variação específica reconhecida usa RAG restrito ao documento,
hash e páginas do contexto, evitando atalhos temáticos mais amplos. Se a
versão do PDF mudar, esse contexto deixa de recuperar evidências até revisão.
Quando um alias exato aponta a um formulário curto sem correspondência lexical
ou semântica suficiente, a busca usa as páginas explicitamente cadastradas,
conferindo o mesmo hash. O limiar semântico global não foi reduzido.
As respostas literais continuam exigindo aprovação humana no manifesto.
Disponibilidade online e igualdade de bytes não comprovam vigência integral.

O acesso programático a ramificações está em
`minerva_dataset.perguntas_relacionadas(pergunta)`. O catálogo SQL espelha o
JSON; após editar o arquivo, execute a sincronização. Nenhum conjunto de
avaliação foi usado para gerar as novas variações nesta etapa.
Ao atualizar também os módulos Python do catálogo, reinicie somente a UI
(`docker compose restart ufpa_rag_ui`) para não manter imports antigos em
memória. Alterações somente no JSON são lidas nas consultas seguintes.

```bash
# instala dependências de dev (pytest + ruff) com uv
uv pip install -r app/requirements-dev.txt

# testes; integração exige MINERVA_TEST_DSN apontando para um banco separado
# a CI fornece PostgreSQL/pgvector; sem DSN, os testes de banco são pulados
pytest

# lint
ruff check .
```

CI (`.github/workflows/ci.yml`) roda Ruff e a suíte com PostgreSQL/pgvector nas branches `main` e `melhorias/roadmap-engenharia`. Cada teste de banco usa schema temporário; configure `MINERVA_TEST_DSN` somente para um banco de testes separado.

A suíte cobre módulos, contratos e integração com banco. Os smoke tests de
navegador registrados no roadmap verificaram chat, referências, isolamento
entre sessões e reload em casos específicos. Esses resultados não cobrem
todas as rotas ou uma avaliação ampla de usabilidade. O plano de avaliação
controlada complementa a suíte com revisão humana e tarefas pela interface.

## Segurança

- Credenciais do Postgres nunca ficam hardcoded no código — vêm de `.env` (gitignored), consumido via variável de ambiente tanto pelo `docker-compose.yml` quanto pelos scripts Python.
- Postgres não é exposto além de `127.0.0.1`.
- Acesso web exige HTTPS da UFPA em cada redirecionamento, rejeita IP privado/reservado e fixa o IP validado na conexão TLS; HTML limitado a 2 MB.
- A geração RAG passa por barreiras institucionais e validação de referências. Isso não autoriza generalizar a revisão para todas as rotas fixas ou para a correção factual de todas as respostas.

## Operação e infraestrutura

Validação de dump custom (`pg_dump -Fc`), em banco temporário separado:

```bash
python3 scripts/validar_backup.py /caminho/backup.dump --relatorio /caminho/restore.json
```

Use um backup recém-criado sem gravações concorrentes para comparar contagens e
hashes. O comando remove somente o banco temporário que criou. Para rollback
da aplicação, preserve o commit anterior e o dump antes de migrar; teste a
restauração, suspenda novas gravações e só então planeje restaurar a base ativa.
As novas colunas são aditivas, mas voltar ao código antigo remove as proteções
de sessão e ingestão. O script de validação não restaura sobre produção.

Expiração de histórico e avaliações é uma operação separada:

```bash
docker compose exec -T ufpa_rag_ui python scripts/retencao_historico.py --dias 30
```

Esse comando apenas simula. Defina o prazo com o responsável pelos dados antes
de usar `--aplicar` ou agendar a exclusão. Nenhuma expiração automática foi
ativada. Logs operacionais omitem respostas bloqueadas e corpos de erro do LLM;
histórico, avaliações e backups ainda contêm texto e devem permanecer privados.

- **Backup diário do Postgres**: `scripts/backup_postgres.sh` (`pg_dump` gzipado, rotação de 14 dias) roda via timer systemd de usuário (`ufpa_rag_backup_postgres.timer`, 03h30, antes do restart do LLM às 4h). Os dumps ficam em `~/ufpa_rag_backups/`, **fora do repositório git** — contêm dado real de aluno (perguntas do chat, respostas abertas do formulário de avaliação) e nunca devem ser versionados. Rodar manualmente: `./scripts/backup_postgres.sh`. Restaurar: `gunzip -c ~/ufpa_rag_backups/ufpa_rag_AAAAMMDD_HHMMSS.sql.gz | docker exec -i ufpa_rag_db psql -U admin ufpa_rag`.
- **Limites de memória** (`mem_limit` no `docker-compose.yml`): `ufpa_rag_llm` 6g, `ufpa_rag_ui` 2g, `ufpa_rag_db` 1g — calibrados com uso real observado, contendo o vazamento de memória conhecido do LLM (ver Limitações abaixo) num teto por container em vez de deixar em aberto. Ao trocar de modelo `.gguf`, ajuste o limite do `ufpa_rag_llm` proporcionalmente ao tamanho do arquivo (o `--mlock` do llama.cpp trava páginas na RAM — um limite menor que o footprint real do modelo o mata no próprio carregamento).
- **Healthcheck nos 3 containers**: `ufpa_rag_db` (`pg_isready`), `ufpa_rag_ui` (`urllib` contra `/_stcore/health` — a imagem `python:3.10-slim` não tem `curl`) e `ufpa_rag_llm` (`curl` contra `/health`, já existia). `docker compose ps` mostra o status real de cada um.
- **Rotação de log** nos 3 serviços (`logging.max-size: 10m`, `max-file: 3`) — sem isso, o log do `ufpa_rag_llm` (uma linha de timing por token gerado) cresce sem limite em produção de longa duração.
- **Rastreamento de rota/latência**: cada linha de `historico_minerva` grava `rota` (qual camada respondeu — nome da rota do `priority_router`, `dataset_ou_basico`, `barreira_institucional`, `rag_generico` ou `rag_cache`) e `latencia_ms`. Permite medir cobertura de rotas e tempo de resposta direto no banco, sem varredura manual:
  ```sql
  SELECT rota, COUNT(*), ROUND(AVG(latencia_ms)) AS media_ms
  FROM historico_minerva
  WHERE rota IS NOT NULL
  GROUP BY rota
  ORDER BY COUNT(*) DESC;
  ```

## Limitações conhecidas

- Inferência em CPU: latências históricas de outros modelos não representam um SLO do Gemma ativo; medir aquecimento, concorrência e p50/p95 antes de comparar.
- Acesso anônimo, sem login institucional. Identidade criada no servidor; `sid` da URL é ignorado. Histórico disponível durante a sessão WebSocket; reload inicia outra identidade. Exporte antes de sair.
- Uma consulta por processo da UI, sem fila de espera; intervalo mínimo de 3 s por sessão e perguntas de até 4.000 caracteres. Réplicas exigirão limitação compartilhada. HTTP do LLM: timeout de conexão de 5 s e leitura de 180 s; streaming verifica prazo entre eventos. Não é cancelamento forçado do processo do modelo.
- **Vazamento de memória do llama.cpp em uso prolongado**: o cache interno de "compute graphs" do servidor cresce sem limite (observado: 11,2GB de RAM depois de dias no ar, contra ~4,5GB esperados de um modelo 7B Q4 — forçava a máquina inteira pro swap e degradava a latência de todos os containers, não só do LLM). Mitigado com um timer systemd de usuário (`ufpa_rag_restart_llm.timer`, reinicia o container `ufpa_rag_llm` diariamente às 4h — ver `systemctl --user list-timers`). Sem estado persistente no container, reiniciar é seguro.



## Histórico da integração V7

Veja [INTEGRACAO_V7.md](INTEGRACAO_V7.md) para o histórico iniciado em
29/10/2026, a configuração dos snapshots e os passos de atualização. As
respostas literais do dataset exigem aprovação verificável; contexto
documental localizado não libera texto fixo. As rotas fixas mantêm revisão
editorial pendente, e o protótipo continua sem login institucional.

A CI cobre `main` e `melhorias/roadmap-engenharia`. A integração e os testes
registrados não constituem homologação integral nem demonstram ganho geral
de qualidade ou latência. As próximas verificações estão descritas no
[plano de avaliação controlada](docs/AVALIACAO_CONTROLADA_V7.md).
