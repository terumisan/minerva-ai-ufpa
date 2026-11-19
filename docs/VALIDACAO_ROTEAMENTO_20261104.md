# Validação operacional do roteamento — 04/11/2026

## Método e ordem

Executada a função `_processar_pergunta` de `main.py`, extraída por AST para
evitar inicializar outra sessão Streamlit, com o roteador, a recuperação
híbrida, o PostgreSQL e o cliente do LLM reais. O worker isolado de manutenção
foi usado para não carregar um segundo embedding no processo da interface.
As perguntas desta rodada são exemplos de diagnóstico; não constituem
holdout independente nem avaliação institucional de vigência.

1. Seis perguntas principais do catálogo: MINERVA_0070, 0071, 0076, 0077,
   0079 e 0090, cobrindo TCC I/II, estágio de 200/390 horas, distribuição
   de horas e aprovação em AC-I/II.
2. Conferência dos PDFs locais, versões SHA-256, páginas físicas,
   trechos recuperados e texto apresentado.
3. Seis formulações naturais ainda não cadastradas, antes de qualquer
   alteração de aliases.
4. Cadastro dos seis aliases explícitos, testes de regressão, sincronização
   QA e repetição com banco e LLM ativos.

## Resultado inicial e revisão das evidências

Todas as seis perguntas principais seguiram para `rag_generico`, com o
contexto documental esperado e seleção de evidências pelo LLM. Todos os
trechos recuperados correspondem ao documento e à versão esperados e
intersectam as páginas físicas cadastradas. Os hashes dos PDFs locais
coincidiram com os contextos. A resposta normativa preservou excertos
documentais, sem publicar prosa normativa gerada.

| Entrada | Evidências apresentadas | Conferência do conteúdo local |
|---|---|---|
| 0070 — TCC I | T:369 e T:367 | Sexto bloco, limite de dependências, calendário e Anexo I assinado |
| 0071 — TCC II | T:369 e T:367 | Aprovação em TCC I, Anexo II e exceções para usar Anexo I |
| 0076 — estágio 200 h | T:64 e T:65 | Blocos I/II e III/IV, além do plano aprovado |
| 0077 — estágio 390 h | T:64 e T:65 | Blocos I/II e V, além do plano aprovado |
| 0079 — horas de AC | T:429 | Total de 120 horas, com mínimo de 60 em cada disciplina |
| 0090 — aprovação em AC | T:430 | Conceito mínimo R, além das horas |

Os trechos de TCC contêm regras de ambas as etapas; a apresentação conserva
as distinções do documento. Há artigos que continuam no trecho seguinte,
e o aviso de incompletude permanece visível. A revisão confirma fidelidade
à cópia local, não completude da norma ou vigência atual.

Antes da correção, cinco formulações novas terminaram em respostas
genéricas com links: duas na rota `tcc`, duas em `internship` e uma em
`atividades_complementares`. A sexta seguiu para recuperação sem contexto
cadastrado e encontrou o trecho de aprovação em AC.

## Alterações

- Centralizada no roteador a proteção do contexto documental, antes
  existente apenas na interface. Consumidores diretos seguem a mesma regra.
- Adicionados seis aliases explícitos e únicos às entradas correspondentes.
  A identificação contextual não usa palavras-chave nem aproximação semântica.
- Testes cobrem todas as perguntas e variações contextuais ativas e fixam
  o destino correto das seis formulações da rodada operacional.
- O prompt de seleção passou a listar os IDs permitidos e explicitar que
  números de artigos, páginas e horas não são IDs de trechos. A validação
  estrita de IDs foi preservada.
- Catálogo QA sincronizado após validar PDFs, páginas e hashes:
  92 perguntas, 316 variações incluindo perguntas principais,
  250 relações e 341 vínculos de evidência.
  Versão publicada: `b947d0ce1a1c18580f48b3582dcf8f92da44ea4e36ca5f4e1933fe3e739f3f0b`.

## Repetição e resultado final

Na primeira repetição após cadastrar os aliases, todas as seis perguntas
chegaram ao contexto correto. Cinco apresentaram evidências; a pergunta
de estágio de 390 horas recebeu `{"ids": [64, 63, 5]}` do LLM, embora só
estivessem disponíveis 62, 64, 63 e 65. A validação rejeitou o ID 5 e exibiu
abstenção. Esse resultado está preservado em `roteamento_novas_depois_20261104.jsonl`.

Após explicitar os IDs permitidos no prompt, a rodada final confirmou:

| Entrada | Rota anterior ao alias | Rota final | IDs apresentados | Duração final |
|---|---|---|---|---|
| 0070 | tcc | rag_generico contextual | 367, 369 | 36,29 s |
| 0071 | tcc | rag_generico contextual | 367, 369 | 32,02 s |
| 0076 | internship | rag_generico contextual | 64, 65 | 25,95 s |
| 0077 | internship | rag_generico contextual | 63, 64, 65 | 34,82 s |
| 0079 | atividades_complementares | rag_generico contextual | 429 | 22,01 s |
| 0090 | rag_generico sem alias | rag_generico contextual | 429, 430 | 24,17 s |

Nos seis casos finais, o contexto identificado é o esperado, o documento,
a versão e as páginas recuperadas conferem, todos os IDs apresentados
existem nas fontes recuperadas e os trechos contêm as condições esperadas.
Essas verificações também passaram nos seis casos principais da primeira
rodada. As durações são observações desta sessão, não um benchmark de modelos.

Validação local final: `pytest -q` com 214 aprovados e 15 ignorados;
`ruff check app` e `git diff --check` passaram. Os testes ignorados dependem
das condições de integração configuradas na suíte; os acessos operacionais
ao PostgreSQL/LLM descritos acima foram reais. O lint global local apontou
E402 em `scripts/atualizar_documentos_ufpa.py`, arquivo não versionado
preexistente que não foi alterado nem incluído neste trabalho.

Limitações: amostra pequena, sem execução de navegador ou do controle de
capacidade da sessão Streamlit. Uma rodada bem-sucedida não elimina falhas
futuras do LLM. Não houve redução das barreiras de referência, inferência
de vigência nem autorização de respostas literais.

## Reprodução e registros

Script resumível: `app/scripts/validar_roteamento_especifico.py`.
Executar dentro do worker de manutenção com `--entrypoint python`:

```sh
python -u scripts/validar_roteamento_especifico.py cadastradas tests/data/roteamento_cadastradas_20261104.jsonl
python -u scripts/validar_roteamento_especifico.py novas tests/data/roteamento_novas_antes_20261104.jsonl
python -u scripts/validar_roteamento_especifico.py novas tests/data/roteamento_novas_depois_20261104.jsonl
python -u scripts/validar_roteamento_especifico.py novas tests/data/roteamento_novas_final_20261104.jsonl
```

Os registros “antes” e “depois” são históricos: reproduzi-los exige,
respectivamente, o catálogo anterior às seis inclusões e o prompt anterior
à lista explícita de IDs. O script ignora perguntas já registradas;
para uma execução nova, informar outro arquivo de saída.

Os JSONL guardam pergunta, rota, contexto esperado/identificado, fontes,
saída do LLM, resposta final, hash do PDF e duração por pergunta. Não
contêm histórico de usuários nem credenciais. Não houve troca de modelo,
embeddings, ingestão ou aprovação de respostas literais.
