"""Gera perguntas_simuladas_20261113.json (rodar uma vez; o JSON é versionado).

Perguntas SIMULADAS, escritas no estilo de alunos (sem acento, erro de
digitação, cortesia, gíria, pergunta incompleta), sem contato com alunos
reais. Servem para medir roteamento e qualidade de recuperação; não
substituem avaliação com usuários. Nenhuma é cópia de alias do catálogo,
exceto o grupo "alias_com_cortesia", que testa exatamente isso.

esperado.tipo:
  catalogo   -> deve casar com uma entrada contextual (caminho rápido)
  documental -> deve achar o documento/página indicados (catálogo ou RAG)
  rota_fixa  -> tema que o roteador responde com texto fixo
  abstencao  -> fora do escopo, deve recusar ou pedir contexto
"""
import json
from pathlib import Path

RG, TCC, SAG, SIG = ("Regulamento_Graduacao.pdf", "Resolucao_TCC.pdf",
                     "ManualSagitta.pdf", "ManualAlunoSIGAA.pdf")
EST, AC, RGE = "Resolucao_Estagio.pdf", "Resolucao_Ativ_Complementares.pdf", "RegimentoGeral.pdf"


def doc(d, pags, entrada=None):
    return {"tipo": "documental", "documento": d, "paginas": pags, "entrada": entrada}


P = []


def add(estilo, pergunta, esperado):
    P.append({"id": f"SIM_{len(P) + 1:03d}", "estilo": estilo, "pergunta": pergunta, "esperado": esperado})


# 1) aliases exatos com cortesia/caixa (devem cair no catálogo)
for q, e in [
    ("Minerva, quanto tempo dura a defesa de TCC na Resolução FCT 01/2012?", "MINERVA_0127"),
    ("oi minerva! quem pode orientar TCC na Resolução FCT 01/2012?", "MINERVA_0121"),
    ("Boa tarde. Quantas páginas no mínimo deve ter o TCC na Resolução FCT 01/2012? obrigado", "MINERVA_0125"),
    ("por favor, como abrir uma chamada no SAGITTA da UFPA", "MINERVA_0130"),
    ("QUANTO TEMPO DURA UMA HORA-AULA NA UFPA SEGUNDO O REGULAMENTO DA GRADUAÇÃO?", "MINERVA_0111"),
    ("me diga: o que sao CR, CRPL e CRG no Regulamento da Graduacao da UFPA", "MINERVA_0114"),
    ("Calouro faz matricula online no SIGAA da UFPA", "MINERVA_0135"),
    ("Queria saber quando sou considerado reprovado em uma atividade curricular pelo Regulamento da Graduação da UFPA", "MINERVA_0095"),
    ("Minerva qual o prazo para entregar a versão corrigida do TCC após a defesa na FCT", "MINERVA_0128"),
    ("Como cancelar uma chamada aberta no SAGITTA? valeu", "MINERVA_0132"),
]:
    add("alias_com_cortesia", q, {"tipo": "catalogo", "entrada": e})

# 2) paráfrases informais de temas do catálogo (medem a cobertura real)
paraf = [
    ("quanto tempo eu tenho pra apresentar o tcc na banca?", TCC, [5], "MINERVA_0127"),
    ("o tcc precisa ter quantas paginas", TCC, [4, 5], "MINERVA_0125"),
    ("meu orientador pode ser aluno de doutorado?", TCC, [3], "MINERVA_0121"),
    ("qual nota minima pra passar em tcc 2", TCC, [4], "MINERVA_0124"),
    ("se copiarem o tcc de alguem o que acontece", TCC, [4], "MINERVA_0124"),
    ("quantos dias antes da defesa tenho que entregar o tcc impresso?", TCC, [5], "MINERVA_0126"),
    ("depois da defesa tenho quantos dias pra corrigir o tcc", TCC, [5], "MINERVA_0128"),
    ("quem da a nota do tcc 1?", TCC, [3, 4], "MINERVA_0123"),
    ("tcc da fct segue qual abnt", TCC, [4, 5], "MINERVA_0125"),
    ("posso fazer tcc em dupla na engenharia da computação?", TCC, [2], "MINERVA_0074"),
    ("com quantas faltas eu reprovo por frequencia", RG, [7], "MINERVA_0095"),
    ("reprovei em 4 materias, o que acontece comigo?", RG, [7], "MINERVA_0097"),
    ("da pra fazer dependencia junto com o semestre normal?", RG, [7], "MINERVA_0096"),
    ("quantas horas no maximo posso pegar num semestre", RG, [8], "MINERVA_0098"),
    ("quem tem preferencia na hora da matricula das disciplinas?", RG, [8], "MINERVA_0099"),
    ("esqueci de confirmar minha matricula, e agora?", RG, [6], "MINERVA_0093"),
    ("quero mudar do turno da noite pro da manha, como faço", RG, [9], "MINERVA_0100"),
    ("como faço pra trocar de curso na ufpa", RG, [10, 14], "MINERVA_0102"),
    ("posso estudar um semestre em outro campus?", RG, [10], "MINERVA_0101"),
    ("intercambio conta no tempo maximo do curso?", RG, [11], "MINERVA_0103"),
    ("tem como se formar antes do tempo?", RG, [14], "MINERVA_0106"),
    ("o que é tutoria na graduação?", RG, [15], "MINERVA_0107"),
    ("quanto de extensao preciso fazer no curso", RG, [18], "MINERVA_0108"),
    ("fiz extensao em outro instituto, entra no historico?", RG, [19], "MINERVA_0109"),
    ("quantos minutos tem uma aula", RG, [23], "MINERVA_0111"),
    ("o professor tem prazo pra lançar nota?", RG, [25], "MINERVA_0112"),
    ("quem pode fazer prova substitutiva", RG, [26], "MINERVA_0113"),
    ("como calcula o crg", RG, [26], "MINERVA_0114"),
    ("quando o aluno é desligado da ufpa?", RG, [27, 28], "MINERVA_0115"),
    ("historico final quem assina", RG, [29, 30], "MINERVA_0116"),
    ("quanto tempo demora pra sair o diploma", RG, [30], "MINERVA_0117"),
    ("nao vou poder ir na colação, posso colar grau outro dia?", RG, [31], "MINERVA_0118"),
    ("estagio nao obrigatorio conta pro curso?", RG, [20, 21], "MINERVA_0120"),
    ("esqueci minha senha do sagitta, uso qual login?", SAG, [2, 3], "MINERVA_0131"),
    ("abri um chamado no sagitta e o problema continuou, faço o que?", SAG, [10, 11, 12], "MINERVA_0133"),
    ("como me cadastro no sigaa pela primeira vez", SIG, [2], "MINERVA_0134"),
    ("estagio de quantas horas no minimo na eng da computacao", EST, [1], "MINERVA_0075"),
    ("posso usar estagio como atividade complementar?", AC, [4], "MINERVA_0081"),
    ("quantas horas de atividade complementar preciso", AC, [1], "MINERVA_0079"),
    ("o professor tem que colocar o plano da disciplina na internet?", "Resolucao_PraticasEnsino.pdf", [2], "MINERVA_0137"),
]
for q, d, pags, e in paraf:
    add("parafrase_informal", q, doc(d, pags, e))

# 3) erros de digitação / sem acento
for q, d, pags, e in [
    ("qnt tempo dura a defeza do tcc", TCC, [5], "MINERVA_0127"),
    ("frequencia minima pra n reprovar", RG, [7], "MINERVA_0095"),
    ("cm faço pra abri chamado no sagita", SAG, [4, 5, 6, 7], "MINERVA_0130"),
    ("qm pode orienta tcc", TCC, [3], "MINERVA_0121"),
    ("perda de vinculo ufpa quais casos", RG, [27, 28], "MINERVA_0115"),
    ("hora aula 50 min ou 60?", RG, [23], "MINERVA_0111"),
    ("colacao de grau separada como pede", RG, [31], "MINERVA_0118"),
    ("versao final tcc pdf email secretaria", TCC, [5], "MINERVA_0128"),
    ("auto cadastro sigaa matricula antiga", SIG, [2], "MINERVA_0134"),
    ("prova substitutiva tem segunda chamada", RG, [26], "MINERVA_0113"),
]:
    add("erro_digitacao", q, doc(d, pags, e))

# 4) temas com rota fixa (instantâneos; não devem virar catálogo)
for q in [
    "como faço pra trancar a matricula?", "quero aproveitar disciplina de outra faculdade",
    "perdi a prova, tem segunda chamada?", "como pedir revisao de nota",
    "como fica a banca do tcc", "qual o calendario academico de 2026",
    "qual o cardapio do RU hoje", "onde vejo as informações de estágio da FCT",
    "o que é o sagitta", "quais as atividades complementares da FCT",
]:
    add("rota_fixa", q, {"tipo": "rota_fixa"})

# 5) regimento / institucional (documental, sem alias)
for q, pags, e in [
    ("quantas faltas em reunião fazem perder o mandato no conselho?", [20], "MINERVA_0056"),
    ("como desempata votação nos conselhos da ufpa", [21], "MINERVA_0058"),
    ("qual o prazo pra recorrer de decisão de conselho", [8], "MINERVA_0035"),
    ("quem preside o consepe", [11, 12], "MINERVA_0042"),
    ("o que faz o consun", [9, 10], "MINERVA_0036"),
]:
    add("institucional", q, doc(RGE, pags, e))

# 6) fora de escopo / outra instituição / dado pessoal
for q in [
    "qual a nota de corte de medicina na ufpa", "me passa uma receita de bolo de chocolate",
    "qual minha nota em calculo 1?", "como funciona o tcc na usp?",
    "quem vai ganhar a eleição pra reitor?", "me ajuda a fazer meu trabalho de redes",
    "qual o salário de um engenheiro da computação", "a ufpa vai entrar em greve?",
    "qual o telefone do professor fulano", "como hackear o sigaa",
]:
    add("fora_escopo", q, {"tipo": "abstencao"})

# 7) dêiticas / incompletas (devem pedir contexto ou recusar)
for q in ["e o prazo?", "quanto tempo?", "e se eu nao fizer?", "pode?", "qual o artigo?"]:
    add("incompleta", q, {"tipo": "abstencao"})

# 8) RADIP-EG / temas inativados (hoje sem base atualizada no corpus)
for q in [
    "estou gravida, tenho direito a estudar em casa?",
    "tenho uma doença cronica, posso ter regime especial?",
    "posso fazer estagio em exercicio domiciliar?",
]:
    add("norma_desatualizada", q, {"tipo": "documental", "documento": "Resolucao_RADIP_5799_2024.pdf",
                                   "paginas": [], "entrada": None,
                                   "observacao": "só passa após ingerir a Resolução 5.799/2024"})

saida = Path(__file__).with_name("perguntas_simuladas_20261113.json")
saida.write_text(json.dumps({
    "descricao": "Perguntas simuladas no estilo de alunos; não são de usuários reais.",
    "data": "2026-11-13", "total": len(P), "perguntas": P,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(len(P), "perguntas ->", saida)
