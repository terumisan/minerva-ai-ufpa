# Roadmap de Engenharia — MINERVA AI V7

> Planejamento proposto em 29/10/2026 para a branch `melhorias/roadmap-engenharia`.
> Planejamento com atualização incremental registrada abaixo; a integração não equivale à homologação de toda a V7.

## 1. Objetivo e escopo

Evoluir a MINERVA para uma versão rastreável, reproduzível e operável: respostas institucionais apoiadas em evidências, atualização documental sem perda da base ativa, histórico protegido e avaliação separada de recuperação, roteamento e geração.

Manter inicialmente Streamlit, PostgreSQL/pgvector, fastembed e llama.cpp. Trocas de modelo, embeddings ou arquitetura dependem de comparação controlada. A identificação da versão anterior e de seu commit deve ser confirmada no primeiro marco; a branch, por si só, não comprova uma release V7.

## 2. Diagnóstico da branch

Leitura documental e estática realizada em 29/10/2026. Não houve execução da aplicação, acesso ao banco de produção nem auditoria completa de segurança.

| Evidência consultada | Situação observada | Consequência para V7 |
|---|---|---|
| [README](README.md) | Descreve roteamento em camadas, RRF, testes, backups, healthchecks e registro de rota/latência | Preservar e verificar esses recursos; não tratá-los como novas entregas |
| [Ingestão](app/scripts/ingestao.py) | Recria a coluna de embedding com commit anterior à ingestão; posteriormente executa TRUNCATE; erros por arquivo são capturados | Uma falha pode deixar a base sem embeddings ou publicar um corpus parcial; adotar staging, validação e ativação atômica |
| [Dataset](app/minerva_dataset.py) | A função de resposta literal exige texto, mas não exige fonte, hash, versão ou validade; a cadeia tenta respostas conhecidas/literais antes de fetch | Formalizar política de respostas verificadas e despacho por estratégia |
| [CI](.github/workflows/ci.yml) | Push e PR configurados apenas para main | Cobrir a branch de engenharia e executar integração com banco |
| [Configuração](app/config.py) | Configuração central depende de Streamlit | Separar configuração do núcleo para facilitar testes e execução por CLI |
| [README](README.md) | Relata ausência de autenticação/rate limiting e histórico identificado por session_id na URL | Tratar autorização e capacidade como bloqueadores da exposição pública da V7 |
| README versus comentário da ingestão | Ambos citam mpnet 768d, mas registram hit-rate@6 de 63,5% e 57,4% em contextos não reconciliados | Vincular cada resultado a corpus, execução e configuração antes de comparar |

O README menciona 57 testes e latência média de aproximadamente 90 segundos no RAG; esses números são relatos do repositório, não medições desta revisão. Quantidade de testes não comprova cobertura do fluxo completo.

## 3. Regras de projeto

1. Preservar a versão anterior por referência Git imutável e backup verificável antes de migrar dados.
2. Separar exemplos de classificação de fatos institucionais. Datasets de perguntas não se tornam fontes factuais por simples correspondência textual.
3. Permitir resposta direta somente com evidência aprovada e vigente. Informação temporal exige revalidação adequada ao assunto.
4. Na falta de evidência, informar a limitação ou solicitar contexto; um link sugerido não conta como resposta factual comprovada.
5. Manter vínculo resposta → trecho → documento → origem e versão.
6. Manter resultados históricos separados de novas execuções. Não atribuir ganhos à V7 antes de medi-los.
7. Não versionar históricos reais, credenciais, backups de produção ou dados pessoais de participantes.

## 4. Marcos e sequência

Estimativa de 12 semanas a partir do início efetivo, considerando um desenvolvedor com apoio periódico de avaliador institucional. Datas e esforço devem ser recalibrados após M0. P0 bloqueia a liberação; P1 integra o escopo de qualidade; P2 é opcional.

| Marco | Janela | Prioridade | Entrega | Dependência | Critério de saída |
|---|---|---|---|---|---|
| M0 — Base reproduzível | Semana 1 | P0 | Inventário, baseline, manifesto e plano de reversão | Nenhuma | Commit, corpus, modelos, ambiente e comandos identificados; restauração ensaiada em ambiente separado |
| M1 — Qualidade e contratos | Semanas 2–3 | P0 | CI ampliada, testes de caracterização e contratos do núcleo | M0 | Lint e testes passam; integração reproduzível com Postgres; fluxo legado preservado nos casos fixados |
| M2 — Corpus e proveniência | Semanas 4–5 | P0 | Migrações, ingestão incremental e publicação atômica | M1 | Reexecução sem duplicatas; falha não altera corpus ativo; fontes recuperáveis por ID e versão |
| M3 — Política de respostas | Semanas 6–7 | P0 | Respostas verificadas, tratamento temporal e recusa fundamentada | M2 | Toda resposta direta aprovada tem evidência válida; casos sem fonte não passam como fatos |
| M4 — Acesso e capacidade | Semanas 8–9 | P0 | Isolamento, controle de acesso, fila limitada e observabilidade | M1; validar com M3 | Testes entre usuários negam acesso cruzado; sobrecarga produz resposta controlada; logs minimizados |
| M5 — Avaliação e otimização | Semanas 10–11 | P1 | Comparação reproduzível, relatório por trilha e ajustes medidos | M2–M4 | Resultados por consulta, parâmetros e limitações disponíveis; revisão de regressões concluída |
| M6 — Homologação e release | Semana 12 | P0 | Candidato V7, manual operacional e plano de rollback | M0–M5 | Todos os bloqueadores fechados e aceite técnico/institucional registrado |

## 5. Backlog executável

Papéis propostos: DEV = desenvolvimento; OPS = operação; VAL = validação institucional/científica. São responsabilidades sugeridas, não atribuições já aceitas. Cada ID abaixo pode ser convertido em uma issue; este documento não cria issues automaticamente.

| ID | Pri. | Responsável | Trabalho e áreas afetadas | Aceite verificável |
|---|---|---|---|---|
| V7-01 | P0 | DEV/OPS | Inventariar commit-base, versões, corpus e artefatos; definir manifesto de execução | Hashes SHA-256, comando, seed quando aplicável, hardware e parâmetros registrados |
| V7-02 | P0 | DEV | Ampliar CI e testes de caracterização em main, roteadores, histórico e recuperação | Push/PR da branch alvo executam checks; testes não dependem de dados de produção |
| V7-03 | P0 | DEV | Separar orquestração da UI e configuração; introduzir contratos de consulta, evidência e resposta | Núcleo testável sem sessão Streamlit; adaptadores preservam comportamento coberto |
| V7-04 | P0 | DEV/OPS | Versionar esquema e migrar corpus por staging, sem DROP/TRUNCATE da base ativa | Falhas de extração, embedding ou banco mantêm a versão ativa; reversão ensaiada |
| V7-05 | P0 | DEV | Deduplicar por hash; manter IDs estáveis, página/seção, URL, data de coleta, versão e modelo de embedding | Duas ingestões idênticas não duplicam trechos; dimensão incompatível é rejeitada antes da ativação |
| V7-06 | P0 | DEV/VAL | Revisar minerva_dataset.py, basic_facts e priority_router; implementar política STATIC_VERIFIED | Texto direto requer trecho, fonte, versão/hash e validação; alterar a fonte invalida a aprovação; estratégia explícita governa despacho |
| V7-07 | P0 | DEV/VAL | Tratar temporalidade, ambiguidade e insuficiência de evidência | Calendário/cardápio fora da validade exigem consulta vigente; falta de curso/ano relevante solicita contexto |
| V7-08 | P0 | DEV | Validar citações e confiança da recuperação | Fonte exibida corresponde a trecho efetivamente utilizado; IDs inventados são rejeitados; limiar definido com dados de desenvolvimento |
| V7-09 | P0 | DEV/OPS | Definir acesso anônimo versus autenticado e autorização do histórico | session_id isolado não autoriza leitura; usuário A não lista, lê, exporta nem apaga conversas de B |
| V7-10 | P0 | DEV/OPS | Limitar requisições, tamanho de entrada, fila e tempo de execução | Carga acima do limite não cria fila ilimitada; timeout/falha do LLM libera recursos e informa estado ao usuário |
| V7-11 | P0 | DEV | Revisar acesso web e tratamento de documentos não confiáveis | Testes de domínio semelhante, redirecionamento externo, endereço privado e instrução maliciosa em documento passam; validação ocorre a cada salto |
| V7-12 | P0 | OPS/DEV | Minimizar logs e definir retenção de histórico, métricas e backups | Logs operacionais sem perguntas/respostas por padrão; exclusão e expiração verificadas; restore em ambiente separado documentado |
| V7-13 | P1 | DEV/VAL | Criar protocolo e executor de avaliação por trilha | Rankings, qrels, previsões e julgamentos exportados por consulta; denominadores e exclusões explícitos |
| V7-14 | P1 | DEV | Medir gargalos e comparar cache, parâmetros de geração e modelos | Comparações no mesmo corpus/hardware; latência p50/p95, memória e qualidade publicadas; melhoria não presumida |
| V7-15 | P1 | DEV/VAL | Melhorar UI: fontes, vigência, status da fila e feedback | Usuário distingue fato sustentado, orientação para fonte e ausência de evidência; navegação por teclado verificada |
| V7-16 | P0 | DEV/OPS/VAL | Homologar candidato, documentar instalação/migração e liberar versão | Instalação limpa, smoke test, restauração e rollback aprovados; changelog e referência da release registrados |

Dependências críticas: V7-04 → V7-05 → V7-06/V7-08 → V7-13. V7-09 a V7-12 podem avançar após os contratos de M1, mas devem ser retestados com o fluxo completo antes da release.

## 6. Contratos e dados propostos

Os nomes a seguir são propostas de implementação, não tabelas já existentes.

- **Documento:** document_id, source_url, título, sha256, versão, collected_at e validade quando aplicável.
- **Trecho:** chunk_id, document_id, página/seção, texto, hash e versão do processamento.
- **Índice:** corpus_version, embedding_model, revisão/hash do modelo, dimensão e configuração de chunking.
- **Resposta:** request_id, rota, status, texto, evidence_ids, corpus_version e tempos por etapa.
- **Resposta verificada:** conteúdo aprovado, evidence_ids, validated_at, política de validade e aprovador.
- **Execução experimental:** run_id, commit, configuração, hashes dos conjuntos e resultados por consulta.

Status de resposta devem distinguir pelo menos: sustentada, orientação para fonte, requer contexto, sem evidência e falha técnica. O armazenamento de texto bruto de consultas deve ser opcional e sujeito à política de retenção.

## 7. Protocolo de avaliação

### Recuperação

Comparar lexical, semântico e híbrido RRF no mesmo corpus e consultas. Registrar Precision@5, Recall@5, MRR e nDCG@5, com qrels e rankings por consulta. Hit-rate@6 pode ser mantido como indicador adicional, identificado separadamente; não é intercambiável com Recall@5.

Se forem usados D720 ou resultados históricos, verificar primeiro quais artefatos existem. Agregados sem rankings/qrels não permitem reconstruir nem comprovar uma reexecução equivalente. Não assumir que a base de 720 perguntas citada na ingestão é idêntica a outro D720 sem comparar hashes e protocolo.

### Roteamento

Medir intenção, macroárea, estratégia, temporalidade e decisão de responder/abster-se conforme os rótulos disponíveis. Publicar macro-F1, acurácia, matriz de confusão e casos de erro. Separar treino/desenvolvimento/teste por grupos de paráfrases e impedir promoção de exemplos do teste para respostas literais antes da avaliação.

Se D1000/D900/D100 forem incorporados, registrar origem e versões; sua presença ou equivalência não foi confirmada nesta revisão da branch.

### Ponta a ponta

Avaliar correção factual, sustentação por evidência, validade das citações, cobertura e abstenções. Definir rubrica antes da execução, registrar denominadores e usar revisão humana independente em uma amostra, com resolução de discordâncias.

### Desempenho

Medir p50/p95 por rota, tempo de recuperação, fila, geração, tokens/s, pico de RAM e falhas. Separar aquecimento e execução fria; registrar concorrência, limites e duração. O relato de 90s do README não deve virar automaticamente um SLO.

### Metas de liberação

- Zero falhas nos testes críticos de isolamento de histórico, ingestão atômica e citação inexistente.
- 100% das entradas habilitadas para resposta direta passam na validação obrigatória de evidência e validade.
- Nenhuma regressão crítica aberta; diferenças de qualidade devem ser analisadas por consulta.
- Limites numéricos de qualidade e latência definidos e registrados em M0 após medir a baseline, antes de otimizar ou abrir o conjunto final de teste.
- Relatar intervalos de confiança quando o tamanho e desenho da amostra permitirem; não anunciar superioridade apenas por diferença pontual.

## 8. Operação, migração e rollback

1. Identificar e preservar a referência da versão anterior, configurações e corpus; fazer backup do banco.
2. Ensaiar restore e migração em banco separado, com dados sintéticos ou sanitizados.
3. Construir e validar o novo corpus em staging; rejeitar publicação parcial inesperada.
4. Ativar o candidato em homologação e executar testes de fluxo, autorização e carga.
5. Liberar com monitoramento de erros, fila, memória e qualidade.
6. Reverter aplicação e ponteiro do corpus se houver regressão crítica. Migrações devem manter compatibilidade durante a janela de rollback; se houver restauração de backup, explicitar perda possível de gravações posteriores e suspender escritas durante a operação.

Metas de RPO/RTO, retenção e capacidade concorrente ficam a cargo de OPS em M0, conforme o ambiente real. Não considerar backup validado sem teste de restauração.

## 9. Riscos e fora de escopo

| Risco | Tratamento |
|---|---|
| Resposta literal desatualizada ou usada fora de contexto | Política de validade, evidência obrigatória e testes negativos de correspondência |
| Mistura de embeddings de modelos/dimensões diferentes | Manifesto de índice e validação antes de ativação |
| Sobreajuste por promover perguntas de avaliação ao dataset | Holdout separado por grupos e congelado antes dos ajustes |
| Memória limitada e inferência serial | Fila limitada, medição de RAM e comparação controlada; não trocar o modelo apenas por velocidade |
| Mudança no HTML de fontes oficiais | Fixtures, detecção de extração vazia, validade do cache e falha explícita |
| Escopo excessivo para 12 semanas | Priorizar P0; adiar P2 e reestimar com evidências de M0 |

Fora do núcleo obrigatório da V7: fine-tuning, troca completa da UI, microserviços, GPU obrigatória, APIs pagas, rastreamento web irrestrito e aquisição incremental automática ampla (C4). Reranking e novos modelos são experimentos P2 após baseline; só entram se demonstrarem benefício sob o orçamento de recursos.

## 10. Checklist de conclusão

- [ ] Baseline, referência anterior e artefatos identificados.
- [ ] CI e testes unitários, integração e fluxo completo aprovados.
- [ ] Migração e ingestão seguras com proveniência verificável.
- [ ] Respostas diretas revisadas; temporalidade e abstenção testadas.
- [ ] Acesso ao histórico protegido; fila, limites e privacidade validados.
- [ ] Relatório experimental reproduzível sem misturar métricas históricas.
- [ ] Manual de instalação, operação, backup/restore e rollback validado.
- [ ] Aceite técnico e institucional registrado; release V7 identificada.

**Estado inicial: planejado.** Consulte a atualização abaixo para entregas parciais; os critérios completos dos marcos permanecem pendentes.



## 11. Integração incremental de 29/10/2026

Base remota: `7d0fffe6e9a5c6730b88395a57f411ccac88d2ed`.
Detalhes, configuração e limites: [INTEGRACAO_V7.md](INTEGRACAO_V7.md).

| Item | Entrega nesta integração | Estado do item completo |
|---|---|---|
| V7-02 | CI também cobre push/PR da branch de engenharia; testes de regressão RRF e snapshots | Parcial; integração com banco/fluxo completo pendente |
| V7-06 | Dataset literal exige fonte HTTPS UFPA, snapshot íntegro e hash da resposta; estratégia explícita governa despacho | Parcial; curadoria das 60 entradas e auditoria das rotas fixas/basic_facts pendentes |
| Recuperação híbrida | Deduplicação por ID em cada lista, desempate estável por ID e preservação das entradas | Implementado e coberto por testes unitários |
| V7-09 | Escopo confirmado: protótipo com acesso anônimo a documentos públicos, sem login institucional/LDAP/SSO | Isolamento do histórico continua pendente; anonimato não elimina essa necessidade |

Não houve migração de banco, retreinamento, troca de embeddings, aprovação
editorial automática nem implantação no servidor. Os números históricos do
README e de artigos não são resultados desta integração. As rotas fixas
anteriores permanecem; não se declara validação universal de respostas.

Validação local desta integração: 125 testes aprovados, Ruff sem erros e
compilação Python concluída; execução em Python 3.12, sem banco ou LLM real.

## 12. Rastreabilidade incremental do RAG — 29/10/2026

Implementado nesta etapa de V7-08:

- O resultado da fusão RRF preserva `id`, documento (`titulo`) e trecho.
- O prompt identifica evidências como `[T:ID]`; a geração deve citar somente
  os trechos utilizados. A aplicação valida todos os IDs citados contra o
  contexto daquela consulta e lista documento/excerto apenas dos IDs citados,
  sem tratar todos os resultados recuperados como usados.
- Referências desconhecidas, malformadas, ausentes ou URLs geradas bloqueiam
  a resposta do modelo e produzem abstenção. Sem evidência identificável,
  não há chamada ao LLM. Não são inferidos links a partir de nomes de PDFs.
- No fallback extrativo, somente os trechos efetivamente reproduzidos (até
  três) são referenciados. A UI aguarda a validação antes de exibir a geração,
  impedindo que referências inválidas apareçam durante o streaming.

Validação executada: **147 testes aprovados** em Python 3.10; Ruff e
compilação Python aprovados. Os novos testes usam fontes sintéticas e cobrem
IDs/documentos preservados, referência válida, subconjunto citado, repetição,
ID inexistente, formato inválido, ausência de evidência, URL gerada, ID ambíguo,
fallback e barreira de exibição no fluxo de `main.processar_pergunta`.
Não foram reexecutados benchmark, avaliação humana, consulta com PostgreSQL/LLM
real ou homologação em navegador nesta etapa.

**V7-08 continua parcial.** Pertencimento ao contexto não comprova que o
excerto sustenta semanticamente cada afirmação, nem que todo enunciado tenha
citação própria. O modelo declara quais evidências utilizou; uso causal não
é observável por este validador. Permanecem pendentes avaliação de sustentação,
confiança/limiares da recuperação, versionamento do corpus, IDs estáveis entre
reingestões e proveniência com página/seção/URL/data. IDs atuais identificam
linhas da base ativa e podem mudar na ingestão destrutiva existente. Documento
e excerto são incluídos no texto exibido/salvo no histórico para consulta;
não foi criada migração nem trilha estruturada independente de auditoria.
Rotas fixas/basic_facts e sua curadoria não foram alteradas.

Esta entrega não conclui M2/M3/M6 nem o roadmap completo. Backups operacionais,
dumps, configurações privadas e logs de consultas permanecem fora do Git.
