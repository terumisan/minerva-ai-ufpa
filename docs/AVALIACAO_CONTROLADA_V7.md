# Avaliação controlada da Minerva AI V7

Plano proposto em 30/10/2026, após a revalidação técnica da branch
`melhorias/roadmap-engenharia`. A rodada ainda não foi executada.

## Objetivo e estado de partida

Verificar se a Minerva orienta o usuário com respostas corretas, sustentadas,
completas para a pergunta e claras sobre suas limitações. O funcionamento da
infraestrutura avançou mais que a validação independente do conteúdo.

O ponto de partida é a suíte com 222 testes aprovados, ingestão incremental
e atômica, catálogo contextualizado e verificações de navegador e restauração.
Essas verificações sustentam a proposta de avaliação controlada. Ainda não
comprovam a qualidade geral das respostas nem homologam a V7.

Recuperar a página correta, citar um trecho existente e responder corretamente
são resultados distintos. A rodada deve examinar cada um deles.

## Amostra e preparação

Revisar entre 20 e 30 perguntas importantes. Uma composição inicial possível
é de 24 casos, distribuídos conforme a tabela. A divisão pode ser ajustada
antes de congelar a amostra, mantendo registro da mudança.

| Tema | Casos sugeridos | Variação de contexto a incluir |
|---|---:|---|
| TCC | 4 | Curso, matrícula, anexos e exceção por mudança ou intervalo |
| Estágio | 4 | Carga horária, pré-requisitos, plano e limite por semestre |
| Matrícula | 4 | Solicitação versus efetivação e informações de curso/ano |
| Atividades complementares | 4 | Distribuição de horas, comprovação e dupla contagem |
| SIGAA e SAGITTA | 4 | Procedimentos e identificação correta do sistema |
| Institucional e controles | 4 | Órgãos diferentes, ausência de evidência e fora de escopo |

Incluir perguntas respondíveis, perguntas que precisam de esclarecimento e
casos em que a resposta esperada é abstenção. Registrar o resultado esperado
antes da execução, sem mostrar essa referência ao sistema.

Um avaliador de conteúdo deve conferir documento, dispositivo, curso,
condições, exceções e vigência aplicáveis a cada caso. Havendo dúvida sobre
vigência, registrar a dúvida e não classificar a resposta como homologada.
Um responsável técnico registra ambiente, configuração e resultados. Esses
papéis são propostos; a atribuição a pessoas ainda precisa ser definida.

As formulações devem ser diferentes das perguntas e das 195 variações usadas
no desenvolvimento. Verificar também sobreposição de intenção, pois trocar
apenas palavras não produz independência. Congelar a amostra e a configuração
antes de executar. Não promover casos dessa rodada ao catálogo durante a
avaliação. Repetições após correções devem ser identificadas como regressão
em desenvolvimento, separadas de uma nova amostra independente.

## Registro por pergunta

Guardar um identificador de caso, a pergunta, o contexto necessário e a
classificação esperada: responder, pedir esclarecimento ou abster-se.
Relacionar a referência esperada ao documento, à versão, à página e ao
dispositivo conferidos pelo avaliador.

Na execução, registrar rota, resposta exibida, IDs e excertos recuperados,
referências efetivamente exibidas e tempo total. Acrescentar tempos de
recuperação e geração quando disponíveis. Identificar commit, versão do
dataset, hashes do corpus/modelo, configuração, hardware, aquecimento e
concorrência. Valores ainda não medidos devem permanecer explicitamente
sem medição.

O registro deve permitir distinguir uma falha de recuperação de uma falha
de geração, uma referência inválida de uma afirmação sem sustentação e uma
abstenção adequada de uma perda de cobertura. Não registrar dados pessoais
desnecessários nas perguntas ou nos relatórios.

## Rubrica de revisão

| Dimensão | O que verificar | Resultado a registrar |
|---|---|---|
| Correção factual | A resposta corresponde à referência conferida? | Correta, parcial, incorreta ou não verificável |
| Sustentação | Os trechos exibidos apoiam as afirmações da resposta? | Sustentada, parcialmente sustentada ou sem suporte |
| Completude e escopo | Foram mantidos curso, órgão, condições e exceções necessários? | Completa para a pergunta, incompleta ou generalizada indevidamente |
| Vigência | A referência foi confirmada como aplicável ao contexto do caso? | Confirmada pelo avaliador ou pendente |
| Citações | Documento, página, versão e trecho correspondem ao material consultado? | Válidas ou inválidas, com descrição da falha |
| Decisão de resposta | Era adequado responder, esclarecer ou abster-se? | Adequada ou inadequada |
| Clareza | O usuário consegue entender a orientação e localizar a fonte? | Clara, exige ajuste ou impede concluir a tarefa |

Avaliar as afirmações relevantes individualmente. Uma resposta com IDs
válidos pode continuar incompleta ou incorreta. A recusa é adequada quando
falta evidência ou contexto necessário; não deve ser penalizada apenas por
não apresentar uma resposta factual.

Registrar como críticos os casos de regra normativa sem suporte, omissão de
condição que altere a orientação, troca de curso/órgão ou exposição de
histórico de outra sessão. A classificação e sua justificativa devem ser
revisadas antes de concluir a rodada. Discordâncias entre avaliadores devem
ser preservadas e resolvidas com referência à fonte.

## Tarefas pela interface

Além de conferir o conteúdo, observar se o usuário consegue formular a
pergunta, compreender a resposta, localizar a fonte e exportar o histórico.
Verificar uso por teclado e entendimento das mensagens de ocupação, falha
e ausência de evidência.

O histórico atual pertence à sessão aberta no servidor. Recarregar a página
inicia outra identidade anônima e não recupera a conversa pela URL. Verificar
se essa informação está clara e se a exportação antes de sair é compreendida.
Isso é uma característica atual, não uma proposta de histórico persistente
entre recarregamentos.

Há uma melhoria de apresentação proposta: mostrar primeiro a orientação e
a referência legível, com documento e página; agrupar hashes, IDs estáveis e
outros detalhes de auditoria em uma área expansível. A rastreabilidade deve
continuar preservada no registro/exportação. Essa alteração ainda não está
implementada e precisa de verificação própria quando for feita.

## Medidas e interpretação

Apresentar os resultados por caso e por dimensão da rubrica. Informar quantas
perguntas foram respondidas, quantas exigiram esclarecimento e quantas tiveram
abstenção, separando decisões adequadas e inadequadas. Explicitar os
denominadores e os casos não verificáveis; não calcular qualidade factual
somente sobre as respostas que deram certo.

Medir latência por rota e informar mediana e p95 quando houver observações
suficientes para descrever a amostra, além de mínimo, máximo e tamanho do
grupo. Separar aquecimento de consultas posteriores e registrar erros e
timeouts. Os números de uma amostra pequena são descritivos: não estabelecem
capacidade concorrente nem um SLO. Os limites aceitáveis de qualidade e
latência devem ser definidos antes da rodada e não ajustados para acomodar
o resultado observado.

Não atribuir ganhos à troca de modelo, ao catálogo ou à V7 sem comparação
controlada no mesmo protocolo. Esta rodada não substitui D720/D1000 nem uma
avaliação estatística representativa.

## Encaminhamento dos resultados

Produzir uma planilha ou relatório por pergunta, uma lista de falhas com
gravidade e um resumo técnico com limitações. Guardar respostas e artefatos
operacionais em pasta privada fora do Git; publicar apenas resumos sem dados
reais de participantes. O prazo de retenção dos históricos e avaliações
continua a ser definido pelo responsável pelos dados; a simulação de 30 dias
não institui uma política automática.

Corrigir falhas críticas e verificar a regressão antes de ampliar o acesso.
Priorizar os erros encontrados e a clareza das respostas antes de aumentar
o catálogo ou experimentar outro modelo. Se houver mudança no sistema,
registrar a nova configuração e separar seus resultados dos anteriores.

A conclusão deve declarar o que foi verificado, o que falhou e o que segue
pendente. Uma rodada sem falhas críticas observadas não autoriza afirmar
ausência de falhas em geral. A homologação e a release V7 continuam sujeitas
aos critérios do [roadmap](../ROADMAP_ENGENHARIA_V7.md).
