# Integração das correções do pacote V7

Base: `7d0fffe6e9a5c6730b88395a57f411ccac88d2ed`, branch
`melhorias/roadmap-engenharia`. Integração em 29/10/2026.

Este documento preserva o histórico da integração inicial e descreve a
configuração necessária para operar a versão atual. A revalidação de
30/10/2026 aprovou 222 testes com PostgreSQL/pgvector, os smoke tests
registrados e a restauração do banco. Consulte a seção final para distinguir
esses resultados dos 125 testes executados na integração de 29/10.

As correções do pacote `MINERVA_V7_ATUALIZADA_20261024.zip` foram adaptadas à
arquitetura desta branch, preservando fastembed/mpnet, Streamlit, PostgreSQL
e o roteamento existente. Não foram copiados os módulos `_v6.py`, datasets,
modelo joblib nem os documentos acadêmicos do pacote antigo.

## Mudanças

- RRF: um ID contribui uma vez por lista; a posição efetiva determina sua
  contribuição. Empates são resolvidos pelo ID. A fusão não altera as entradas.
- Dataset: `RESPOSTA_LITERAL` e `STATIC_VERIFIED` exigem snapshot local íntegro,
  URL HTTPS da UFPA e hash da resposta autorizada. Informação temporal é
  rejeitada nessa rota. Sem autorização, retorna `None` para o RAG prosseguir.
- `RAG_WEB_CONTROLADO` obedece à estratégia e não responde usando texto literal
  ou um fato de entidade incidentalmente presente na entrada.
- A aprovação também é invalidada ao editar a resposta, além de alterar a fonte.

O escopo de snapshots é o dataset. As rotas fixas e `basic_facts` continuam
com seu comportamento anterior; a auditoria integral dessas respostas permanece
no roadmap. Não se declara que todas as respostas do sistema estão validadas.

## Configuração de respostas literais

No Docker Compose, `./static_snapshots` é montado somente para leitura em
`/static_snapshots`. Fora do Docker, defina `MINERVA_V7_STATIC_SNAPSHOT_DIR`
com o caminho absoluto da pasta. Não é necessário login institucional.

Após verificar a fonte e sua relação com a resposta, o curador deve preencher
`url_oficial` na entrada do dataset e criar `static_manifest.json`:

```json
{
  "ID_DA_ENTRADA": {
    "file": "fonte.txt",
    "url": "https://fct.ufpa.br/",
    "sha256": "SHA256_DOS_BYTES_DA_FONTE",
    "answer_sha256": "SHA256_DA_RESPOSTA_LITERAL_COM_STRIP_EM_UTF8",
    "reviewer": "IDENTIFICADOR_DO_CURADOR",
    "validated_at": "DATA_ISO_8601_COM_FUSO",
    "valid_until": "DATA_ISO_8601_COM_FUSO"
  }
}
```

Os valores acima são placeholders, não uma aprovação. Hashes comprovam
integridade local, não correção factual ou vigência online. A curadoria e
revalidação continuam humanas. A pasta é ignorada pelo Git; não inclua segredos.
Nenhuma resposta foi aprovada automaticamente. Na integração inicial, havia
60 entradas literais legadas; após as ampliações documentadas, o catálogo
contém 87 entradas literais contextualizadas, das quais 86 estão ativas, além
das cinco entradas de outras estratégias. Uma duplicata foi preservada
inativa. As respostas literais permanecem sem autorização automática, mesmo
quando já possuem contexto e URL confirmada. Isso pode aumentar a latência
e as abstenções até a curadoria ser concluída.

Atualização de 30/10: aprovações exigem revisor e datas com fuso; validação
futura, validade expirada e ausência desses campos bloqueiam a resposta.
Manifestos antigos precisam de reavaliação humana. Inventário de pendências:
`docker compose exec -T ufpa_rag_ui python scripts/auditar_literais.py`.

## GitHub, nuvem e execução

GitHub armazena o código. O chatbot precisa de um host com Docker, modelo GGUF,
PDFs e banco persistente. Atualizar o repositório não copia modelos ou PDFs e
não sincroniza o banco automaticamente. Esses artefatos permanecem no host,
com backup e procedimentos de atualização próprios.

Para uma instalação nova em um host com Docker:

```bash
git clone --branch melhorias/roadmap-engenharia https://github.com/terumisan/minerva-ai-ufpa.git
cd minerva-ai-ufpa
cp .env.example .env
# Defina DB_PASSWORD no .env; prepare models/ e documentos/ conforme README.
docker compose up -d --build
```

Abra `http://localhost:8501` no host. Em servidor remoto, use o acesso configurado
nesse servidor. O modelo exigido pelo Compose atual está em `models/gemma-4-E4B_q4_0-it.gguf`.
O banco novo precisa da ingestão e da publicação do catálogo descritas no
README. Use o worker isolado para processar os PDFs e depois execute
`scripts/sincronizar_qa.py`. O publicador exige que os PDFs e suas versões
correspondam aos contextos cadastrados; divergência precisa de revisão.
Preserve backup antes de atualizar uma base existente.

Para uma instalação existente, revise `git status`, preserve alterações locais
e o backup e atualize a branch com `git pull --ff-only`. Reconstrua a imagem
quando as dependências ou o Dockerfile mudarem; reinicie a UI ao alterar
módulos Python para carregar os imports novos. Execute o worker de ingestão
quando houver atualização do corpus ou migração ainda não aplicada: arquivos
inalterados são ignorados. Após mudanças no catálogo, sincronize o QA.

## Validação inicial — 29/10/2026

Comandos: `python -m pytest -q`, `python -m ruff check .` e
`python -m compileall -q app`. Testes usam fontes sintéticas e não aprovam
conteúdo institucional real. Na integração inicial não foram reexecutados
D720, D1000, inferência com GGUF nem integração com PostgreSQL. Esses limites
descrevem aquela execução; não devem ser confundidos com as verificações
operacionais posteriores.

Validação local em 29/10/2026: **125 testes passaram**, Ruff sem erros e
compilação Python concluída. Ambiente: Python 3.12, pytest 9.1.1, Ruff 0.15.20;
a CI daquela etapa ainda precisava confirmar a compatibilidade com Python 3.10.

## Estado verificado e próximos passos — 30/10/2026

A revalidação posterior usou Python 3.10.20 e aprovou 222 testes com
PostgreSQL/pgvector, sem skips, além de Ruff, compilação e CI. Foram repetidas
as 86 recuperações contextuais ativas, duas variações com o LLM real, os
fluxos de TCC e SAGITTA no navegador e a restauração de nove tabelas em banco
separado. A base manteve 413 trechos de 15 documentos. O [roadmap](ROADMAP_ENGENHARIA_V7.md)
registra os resultados e os artefatos locais de cada rodada.

Essa evidência verifica funcionamento e regressões específicas. O catálogo
de desenvolvimento não é uma amostra independente de qualidade; uma citação
válida também não comprova completude ou vigência. Não foram repetidos os
benchmarks históricos D720/D1000 nem comparações entre modelos.

A próxima etapa proposta é uma avaliação controlada de 20 a 30 perguntas,
com revisão das fontes e formulações diferentes das usadas no desenvolvimento.
O [plano de avaliação](docs/AVALIACAO_CONTROLADA_V7.md) define a rubrica e o
registro de correção factual, sustentação, abstenções, clareza e latência.
Melhorias visuais nas fontes e nos detalhes de auditoria são propostas;
esta atualização documental não altera a interface nem autoriza respostas
literais. O prazo de retenção e a homologação institucional seguem pendentes.
