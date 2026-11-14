# Responsividade para celulares e tablets — 04/11/2026

## Alterações

- Corrigidos seletores antigos de coluna para o componente `stColumn` do
  Streamlit instalado. Regras das grades ficam restritas aos acessos rápidos,
  sem modificar todas as colunas de formulários ou menus do aplicativo.
- Até 1024 px: categorias e sugestões em duas colunas, margens ajustadas,
  cabeçalho com logo/título/tema e controles de toque com altura mínima
  de 44 px. Ações de resposta permanecem em uma linha.
- Até 600 px: tema em uma segunda linha no cabeçalho, logo compacto,
  menor recuo nas mensagens e avatar reduzido para favorecer a leitura.
- Até 360 px: acessos rápidos em uma coluna para acomodar rótulos longos.
- Campo de pergunta com texto de 16 px em celulares/tablets, botão de envio
  com alvo de 44 px e preservação do espaço seguro inferior do dispositivo.
- Barra lateral limitada à largura disponível, com os controles nativos
  de abrir/fechar preservados e o controle de fechar sempre visível nas
  telas menores. Botão de copiar ajustado a 44 px de altura.

Não foram alterados roteamento, conteúdo dos documentos, identidade anônima
ou política de preservação do histórico. O processo da interface foi
reiniciado para carregar as alterações de CSS e componentes importados.

## Validação

Roteiro em Chromium com eventos de toque habilitados, contra o Streamlit,
banco e LLM reais. A mesma conversa foi redimensionada entre retrato e
paisagem. Uma pergunta sintética de TCC II foi usada para verificar a
apresentação de excertos, fontes e ações.

| Largura × altura | Perfil verificado |
|---|---|
| 320 × 740 | Celular estreito |
| 390 × 844 | Celular |
| 600 × 960 | Tablet compacto |
| 768 × 1024 | Tablet em retrato |
| 820 × 1180 | Tablet em retrato |
| 1024 × 768 | Tablet em paisagem |
| 1180 × 820 | Tablet largo/desktop compacto |
| 1440 × 1000 | Regressão de desktop |

O roteiro confere página inicial e chat em cada tamanho: ausência de
transbordamento horizontal, cabeçalho e seletor de tema dentro da largura,
campo de pergunta dentro da tela, fonte de 16 px até 1024 px e ações
alinhadas com altura mínima de 44 px nas telas menores. Confere também
seleção de categoria, troca de tema e navegação lateral em 390 e 820 px.

Resultado final: **16 layouts e duas verificações de navegação aprovados**,
sem exceções JavaScript. Registros no
[JSON da execução](../app/tests/data/responsividade_20261104.json).
Capturas: [início em celular](figures-responsive-20261104/home_390.png),
[início em tablet](figures-responsive-20261104/home_768.png),
[chat em 320 px](figures-responsive-20261104/chat_320.png),
[chat em tablet paisagem](figures-responsive-20261104/chat_1024.png) e
[navegação lateral](figures-responsive-20261104/sidebar_390.png).

Suíte local: **221 testes aprovados e 15 ignorados**; `ruff check app`,
`git diff --check` e verificação de sintaxe do roteiro Node aprovados.

São verificações de viewport em Chromium, não ensaios em aparelhos físicos.
Safari/iOS, abertura do teclado virtual, leitores de tela e todos os
formulários da aplicação não foram validados nesta rodada.

## Reprodução

Roteiro: `scripts/validar_responsividade_minerva.cjs`. Com Playwright e
Chromium disponíveis, executar:

```sh
NODE_PATH=/tmp/minerva-browser/node_modules node scripts/validar_responsividade_minerva.cjs
```

`MINERVA_CHROMIUM_EXECUTABLE` seleciona um Chromium fora da instalação
padrão do Playwright; `MINERVA_UI_URL` seleciona o endereço da interface;
`MINERVA_UI_ARTIFACT_DIR` define o destino dos registros e capturas.
`--navegacao` executa apenas a verificação dos controles laterais sem
consultar o LLM. A rodada completa grava uma pergunta sintética no histórico
da sua própria sessão de teste.
