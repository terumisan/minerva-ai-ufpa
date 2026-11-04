# Validação da interface — 04/11/2026

## Escopo

Rodada técnica no Chromium com o Streamlit em `localhost:8501`, PostgreSQL
e LLM ativos. Foram verificados, nesta ordem, clareza e localização das
fontes, reformulação e perguntas relacionadas, espera, abstenção e histórico.
As perguntas são sintéticas de diagnóstico, sem participantes externos.
Esta rodada não é um estudo de usabilidade nem homologação de vigência.

## Problemas encontrados e alterações

Na primeira abertura, o processo Streamlit ainda usava os módulos antigos
em memória e apresentou a resposta temática genérica para a formulação de
TCC II já corrigida nos arquivos. O bind mount foi conferido e a interface
foi reiniciada para carregar os módulos novos. A entrega de futuras mudanças
em módulos importados deve incluir reinício controlado e smoke test no navegador;
testar um processo Python separado não verifica a versão em memória da UI.

Após esse reinício, as referências corretas apareceram, mas o texto da norma
ficava misturado a hashes extensos e era exibido em fonte monoespaçada.
As relações do catálogo não tinham controles clicáveis no chat. O spinner
não mostrava tempo decorrido. A abstenção não orientava como reformular.
Em tela estreita, as ações da resposta ficavam empilhadas.

Alterações realizadas:

- Texto dos excertos em apresentação normal, com documento, página e ID.
  Botão **Abrir fonte oficial** aponta para o PDF com fragmento `#page=N`.
  Hashes e a referência integral permanecem em **Detalhes da fonte**.
- **Perguntas relacionadas** permite enviar a pergunta completa cadastrada.
  Somente a resposta mais recente oferece esses botões; perguntas posteriores
  seguem a mesma recuperação e validação do chat.
- Orientação explícita de que cada pergunta é consultada separadamente.
  A abstenção sugere informar curso, assunto e norma ou documento.
- Indicador nativo de tempo decorrido durante a consulta.
- Ações de resposta alinhadas em uma linha em tela estreita.

O conteúdo salvo, copiado e exportado continua integral, incluindo as
referências. Não houve alteração de matching, corpus, embeddings, modelo,
validação de IDs ou autorização de respostas literais nesta rodada.

## Verificações

O roteiro usa a formulação de matrícula em TCC II, aciona pelo botão a
pergunta sobre mudança de orientador/tema/intervalo e verifica uma pergunta
sem evidência sobre uma sala fictícia em Marte. Também confere os links,
abre e fecha os detalhes, mede a espera e compara exportações antes e depois
de trocar de conversa e restaurá-la.

Uma segunda sessão abre a URL da primeira para conferir que o identificador
de conversa não dá acesso ao histórico. O reload deve iniciar uma sessão
vazia, conforme o aviso já existente na barra lateral. O histórico deve ser
exportado antes de recarregar ou sair; essa regra foi preservada.

Testes locais: **221 aprovados e 15 ignorados**, `ruff check app` e
`git diff --check` aprovados. Sete testes novos verificam preservação de
excertos/rastreabilidade, fallback integral para formatos desconhecidos,
URLs oficiais e apresentação literal de texto documental. Também foi
conferida a preservação dos excertos das 12 respostas com fontes registradas
na rodada anterior de roteamento.

O script não versionado preexistente `scripts/atualizar_documentos_ufpa.py`
foi preservado fora da alteração; seu E402 continua fora do lint de `app/`.

## Resultado final no navegador

| Verificação | Resultado |
|---|---|
| Formulação natural sobre matrícula em TCC II | Excertos com documentação e condições da resolução |
| Acesso às fontes | Dois botões apontam para PDF oficial e página física; detalhes abrem/fecham |
| Pergunta relacionada por clique | Enviada integralmente; retorno contém a exceção sobre Anexo I |
| Espera | Spinner e tempo decorrido observados nas duas consultas documentais |
| Abstenção | Pergunta sem evidência recebe a limitação e orientação de reformulação |
| Trocar e restaurar conversa | Exportações antes/depois idênticas, com as três perguntas |
| Outra sessão com a mesma URL | Nenhuma mensagem da sessão anterior foi exibida |
| Recarregar | Histórico visual vazio, conforme a regra de sessão anônima |
| Tela de 390 × 844 px | Sem transbordamento horizontal; ações da resposta em uma linha |
| JavaScript | Nenhuma exceção de página na execução final |

Na execução final, os tempos totais observados foram 1,806 s para a
formulação de TCC II, 21,201 s para a pergunta relacionada e 0,722 s para
a abstenção. São consultas repetidas após aquecimento; não representam
estimativa de primeira consulta ou garantia de tempo máximo.

Registros: [JSON da execução final](../app/tests/data/validacao_interface_20261104.json).
Capturas: [antes](figures-ui-20261104/resposta_antes.png),
[depois](figures-ui-20261104/resposta.png),
[tela estreita](figures-ui-20261104/mobile_resposta.png),
[espera](figures-ui-20261104/espera.png) e
[abstenção](figures-ui-20261104/abstencao.png).

A verificação dos botões confere os destinos dos links e o fragmento de
página; não revalida disponibilidade remota nem vigência dos PDFs oficiais.
Permanecem pendentes avaliação de clareza por usuários e revisão institucional
do conteúdo. Perguntas curtas que dependem de contexto anterior ainda precisam
ser reformuladas explicitamente; não foi introduzida interpretação implícita
do histórico.

## Reprodução

Roteiro: `scripts/validar_interface_minerva.cjs`. Requer Node, Playwright e
Chromium. O teste foi executado com Playwright 1.64.1 e o Chromium headless
já disponível na máquina. Para preparar uma instalação isolada:

```sh
npm install --prefix /tmp/minerva-browser playwright@1.64.1
NODE_PATH=/tmp/minerva-browser/node_modules node scripts/validar_interface_minerva.cjs final
```

Se o Chromium estiver fora da instalação padrão do Playwright, definir
`MINERVA_CHROMIUM_EXECUTABLE`. `MINERVA_UI_URL` permite selecionar o endereço
da interface; `MINERVA_UI_ARTIFACT_DIR` define a pasta dos resultados.
O roteiro usa uma sessão nova e grava perguntas sintéticas no histórico do
aplicativo. Deve ser executado depois de a interface terminar de iniciar.

O LLM atingiu 5,99 GiB do teto de 6 GiB durante as rodadas e foi reiniciado,
seguindo a mitigação já documentada. Não foi tratado como ganho ou regressão
de desempenho da interface. As durações observadas incluem as condições
desta sessão e não constituem benchmark.
