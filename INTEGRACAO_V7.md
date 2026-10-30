# Integração das correções do pacote V7

Base: `7d0fffe6e9a5c6730b88395a57f411ccac88d2ed`, branch
`melhorias/roadmap-engenharia`. Integração em 29/10/2026.

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
Nenhuma resposta foi aprovada automaticamente nesta integração. As 60 entradas
literais legadas sem manifesto/URL válida deixam de responder diretamente;
isso pode aumentar a latência e as abstenções até a curadoria ser concluída.

Atualização de 30/10: aprovações exigem revisor e datas com fuso; validação
futura, validade expirada e ausência desses campos bloqueiam a resposta.
Manifestos antigos precisam de reavaliação humana. Inventário de pendências:
`docker compose exec -T ufpa_rag_ui python scripts/auditar_literais.py`.

## GitHub, nuvem e execução

GitHub armazena o código. O chatbot precisa de um host com Docker, modelo GGUF,
PDFs e banco persistente. O ambiente desta conversa não hospeda uma aplicação
permanente nem sincroniza automaticamente pastas do computador.

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
O banco novo ainda precisa da ingestão descrita no README; não a execute sobre
uma base existente sem backup. A ingestão atual é incremental e atômica;
consulte o README para migração aditiva, memória e limites.

Para uma instalação existente, revise `git status`, preserve alterações locais
e só então atualize a branch com `git pull --ff-only` e reconstrua os containers.
Não é necessário reingerir documentos para estas correções.

## Validação e limites

Comandos: `python -m pytest -q`, `python -m ruff check .` e
`python -m compileall -q app`. Testes usam fontes sintéticas e não aprovam
conteúdo institucional real. Não foram reexecutados D720, D1000, inferência
com GGUF nem integração com PostgreSQL. Não se atribuem ganhos de precisão
ou velocidade à integração antes de medi-los.

Validação local em 29/10/2026: **125 testes passaram**, Ruff sem erros e
compilação Python concluída. Ambiente: Python 3.12, pytest 9.1.1, Ruff 0.15.20;
a CI do projeto usa Python 3.10 e deve confirmar a compatibilidade nesse alvo.
