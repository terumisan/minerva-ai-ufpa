from minerva_priority_router import _norm, _official_ufpa_url, _tokens, classify_question


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
