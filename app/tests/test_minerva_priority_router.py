from minerva_priority_router import (
    _norm,
    _official_ufpa_url,
    _tokens,
    classify_question,
    priority_answer,
)


def test_official_ufpa_url_dominio_raiz():
    assert _official_ufpa_url("https://ufpa.br/pagina")


def test_official_ufpa_url_subdominio():
    assert _official_ufpa_url("https://fct.ufpa.br/index.php/contato")


def test_official_ufpa_url_rejeita_dominio_parecido():
    # "ufpa.br.evil.com" tem ufpa.br como prefixo, não como domínio real —
    # não pode ser aceito como oficial.
    assert not _official_ufpa_url("https://ufpa.br.evil.com/pagina")


def test_official_ufpa_url_rejeita_dominio_diferente():
    assert not _official_ufpa_url("https://ufpe.br/pagina")


def test_official_ufpa_url_rejeita_scheme_invalido():
    assert not _official_ufpa_url("ftp://ufpa.br/arquivo")


def test_official_ufpa_url_rejeita_url_malformada():
    assert not _official_ufpa_url("não é uma url")
    assert not _official_ufpa_url("")


def test_norm_remove_acentos_e_normaliza_espacos():
    assert _norm("Trancamento  de   Matrícula!") == "trancamento de matricula"


def test_tokens_extrai_palavras():
    assert _tokens("Calendário Acadêmico 2026") == {"calendario", "academico", "2026"}


def test_classify_question_cardapio_retorna_menu():
    assert classify_question("Qual é o cardápio do RU hoje?") == "menu"


def test_classify_question_tcc():
    assert classify_question("Quero saber o regulamento do TCC") == "tcc"


def test_classify_question_nao_string_retorna_none():
    assert classify_question(None) is None
    assert classify_question(123) is None


def test_classify_question_vazia_retorna_none():
    assert classify_question("   ") is None


def test_classify_question_outra_unidade_sem_fct_nao_usa_rota_fct():
    # Bug real documentado no código: "localização do CTIC" não pode cair
    # na rota "contact" (que é específica da FCT).
    resultado = classify_question("Qual a localização do CTIC?")
    assert resultado != "contact"


def test_classify_question_matricula_variacoes_comuns():
    # Bug real (achado por medição de latência): "onde/como posso me
    # matricular" não tinha nenhuma rota fixa e caía sempre no RAG
    # genérico (2-5min em CPU), apesar de ser resposta institucional
    # estável e uma das perguntas mais frequentes de alunos novos.
    variacoes = [
        "Onde posso me matricular?",
        "Como faço minha matrícula?",
        "Como me matricular na UFPA?",
        "Quero me matricular",
        "matrícula",
    ]
    for pergunta in variacoes:
        assert classify_question(pergunta) == "enrollment", pergunta


def test_classify_question_matricula_em_estagio_continua_internship():
    # Não pode regredir: pergunta com "estágio" continua roteada para
    # internship, e não para a nova rota "enrollment" (o check de
    # "estagio" vem antes no classify_question).
    pergunta = "Quem pode solicitar a matrícula em Estágio Supervisionado?"
    assert classify_question(pergunta) == "internship"


def test_classify_question_matricula_especifica_nao_intercepta_dataset():
    # Não pode regredir: uma pergunta específica já coberta por entrada
    # RESPOSTA_LITERAL do dataset (minerva_dataset.json) não deve ser
    # engolida pela rota genérica de matrícula — o priority_router roda
    # antes do dataset no pipeline, então "enrollment" precisa devolver
    # None aqui para a pergunta seguir até o dataset.
    pergunta = "O que acontece após a solicitação de matrícula?"
    assert classify_question(pergunta) is None


def test_classify_question_base_direcao_fct_nao_e_sequestrada_por_rota_basica():
    # Bug real (achado por medição de latência): "Quem é a atual direção
    # do FCT?" contém "FCT". A camada de fatos básicos (classify_question
    # rebindado no fim do arquivo — ver _minerva_router_before_basic_classify)
    # reivindicava essa pergunta como "basic_acronym" antes do roteador
    # original decidir algo, mas a extração de sigla falhava (extraía
    # "ATUAL" em vez de "FCT") e devolvia None — sem nunca chegar à rota
    # "leadership", que cobre "direcao" corretamente. Resultado: a
    # pergunta caía direto no RAG genérico (2-5min) apesar de ter rota
    # instantânea pronta. O fix usa _classify_question_base (referência à
    # função original, capturada antes do rebind) dentro de
    # priority_answer, em vez do nome global "classify_question" — sujeito
    # a late binding e resolvido para a versão sequestrada a cada chamada.
    #
    # Testa _classify_question_base diretamente, não o classify_question
    # público (que continua devolvendo "basic_acronym" por design — ver
    # seu próprio docstring) nem priority_answer (cuja rota "leadership"
    # faz scrape ao vivo da página da FCT quando de fato responde).
    from minerva_priority_router import _classify_question_base

    assert _classify_question_base("Quem é a atual direção fo FCT?") == "leadership"


def test_classify_question_matricula_quando():
    # Gap encontrado na mesma varredura: a rota de matrícula só cobria
    # "onde/como", não "quando".
    assert classify_question("Quando posso me matricular?") == "enrollment"


def test_classify_question_calendario_periodo_letivo():
    # Gap encontrado na mesma varredura: pergunta real do histórico de
    # conversas (2 ocorrências) sem cobertura na rota de calendário.
    assert classify_question("Quando começa e termina o período letivo?") == "calendar"


# ----------------------------------------------------------------------
# Rotas encontradas varrendo os portais FCT/UFPA em busca de lacunas
# (trancamento, aproveitamento, guia do calouro, atividades complementares)
# ----------------------------------------------------------------------

def test_classify_question_trancamento_variacoes():
    variacoes = [
        "Como eu posso trancar o curso?",
        "Quero trancar minha matrícula",
        "Como faço para trancar?",
    ]
    for pergunta in variacoes:
        assert classify_question(pergunta) == "matricula_trancamento", pergunta


def test_classify_question_aproveitamento_variacoes():
    variacoes = [
        "Como solicitar aproveitamento de disciplinas?",
        "Quero saber sobre equivalência de disciplinas",
        "Existe dispensa de disciplina na FCT?",
    ]
    for pergunta in variacoes:
        assert classify_question(pergunta) == "aproveitamento_estudos", pergunta


def test_classify_question_guia_calouro_variacoes():
    variacoes = [
        "Sou calouro, o que preciso saber?",
        "Tem algum guia para os calouros?",
        "Acabei de entrar na FCT",
    ]
    for pergunta in variacoes:
        assert classify_question(pergunta) == "guia_calouro", pergunta


def test_classify_question_atividades_complementares():
    assert (
        classify_question("Como faço para integralizar atividades complementares?")
        == "atividades_complementares"
    )


def test_priority_answer_trancamento_cita_regulamento_e_prazo():
    resposta = priority_answer("Como eu posso trancar o curso?")
    assert resposta is not None
    assert "2 períodos letivos consecutivos" in resposta
    assert "PROEG" in resposta or "regulamento-da-graduacao" in resposta.lower()


def test_priority_answer_aproveitamento_cita_regulamento():
    resposta = priority_answer("como solicitar aproveitamento de disciplinas?")
    assert resposta is not None
    assert "AE" in resposta


def test_priority_answer_guia_calouro_cita_fonte():
    resposta = priority_answer("Sou calouro, o que preciso saber?")
    assert resposta is not None
    assert "caecomp" in resposta.lower()


def test_novas_rotas_nao_regridem_enrollment_nem_internship():
    # As novas rotas (trancamento, aproveitamento, calouro, atividades
    # complementares) foram inseridas depois de "enrollment" na ordem do
    # classify_question — garantindo que não capturam por engano perguntas
    # já cobertas por rotas anteriores.
    assert classify_question("Onde posso me matricular?") == "enrollment"
    assert classify_question("Quais são as regras de estágio?") == "internship"


# ----------------------------------------------------------------------
# Rotas encontradas continuando a varredura em domínios UFPA/FCT
# (laboratórios de pesquisa/ensino, PPGCC)
# ----------------------------------------------------------------------

def test_classify_question_laboratorios_pesquisa_lista_geral():
    assert classify_question("Quais laboratórios de pesquisa a FCT tem?") == "laboratorios_pesquisa"


def test_classify_question_laboratorios_pesquisa_sigla_especifica():
    # "O que é X?" também casa com a checagem de sigla básica (mesma
    # nuance do teste de "direção do FCT" acima) — o classify_question
    # público pode devolver "basic_acronym" para essas frases por design.
    # O que importa é a resposta final: testamos _classify_question_base
    # (usada internamente por priority_answer, ver bug fix acima) e uma
    # frase sem esse padrão de sigla para o classify_question público.
    from minerva_priority_router import _classify_question_base

    for pergunta in ["O que é o GERCOM?", "Me fale sobre o LASSE", "O que é o LEA?"]:
        assert _classify_question_base(pergunta) == "laboratorios_pesquisa", pergunta

    assert classify_question("Fale sobre o GERCOM") == "laboratorios_pesquisa"


def test_classify_question_laboratorios_pesquisa_nao_casa_substring_solta():
    # "lea" e "lct" são siglas curtas — o regex usa \b para não disparar
    # dentro de outra palavra (ex.: "linear", "aleatorio").
    assert classify_question("Isso é um problema linear e aleatório") != "laboratorios_pesquisa"


def test_classify_question_laboratorios_ensino():
    for pergunta in ["Onde fica o Labcom?", "Que softwares tem no laboratório de ensino?"]:
        assert classify_question(pergunta) == "laboratorios_ensino", pergunta


def test_classify_question_ppgcc():
    assert classify_question("Tem mestrado em ciência da computação?") == "ppgcc"


def test_priority_answer_laboratorio_especifico_cita_foco_de_pesquisa():
    # "Fale sobre" (em vez de "O que é") evita a checagem de sigla básica
    # (classify_basic_question), que faria priority_answer tentar uma
    # busca de rede ao vivo para "GERCOM" antes de desistir e cair na
    # rota certa — mesmo resultado final, sem depender de rede no teste.
    resposta = priority_answer("Fale sobre o GERCOM")
    assert resposta is not None
    assert "redes" in resposta.lower()
    assert "laboratorios-de-pesquisa" in resposta


def test_priority_answer_laboratorios_ensino_cita_labcom():
    resposta = priority_answer("Onde fica o Labcom?")
    assert resposta is not None
    assert "Laboratório de Computação" in resposta


def test_priority_answer_ppgcc_nao_afirma_doutorado_nao_confirmado():
    # A página oficial só confirma mestrado — a resposta não pode afirmar
    # doutorado, que não está confirmado na fonte.
    resposta = priority_answer("Tem mestrado em ciência da computação?")
    assert resposta is not None
    assert "doutorado" not in resposta.lower()


def test_novas_rotas_lab_nao_regridem_professores_nem_ppgee():
    assert classify_question("Quem são os professores da FCT?") == "faculty"
    # PPGEE já tem entrada dedicada em minerva_basic_facts.py — a rota
    # nova de PPGCC não deve interferir na classificação de PPGEE.
    from minerva_basic_facts import classify_basic_question
    assert classify_basic_question("O que significa PPGEE?") == "basic_acronym"
