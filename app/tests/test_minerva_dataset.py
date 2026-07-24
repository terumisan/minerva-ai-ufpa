from minerva_dataset import _norm, _pergunta_bate, _resposta_literal


def test_norm_remove_acentos_e_pontuacao():
    assert _norm("Matrícula: como funciona?") == "matricula como funciona"


def test_pergunta_bate_por_correspondencia_exata():
    entrada = {"pergunta": "Como faço a matrícula do TCC?", "variacoes": []}
    assert _pergunta_bate(_norm("Como faço a matrícula do TCC?"), entrada)


def test_pergunta_bate_por_variacao():
    entrada = {
        "pergunta": "pergunta principal",
        "variacoes": ["Quero me matricular no TCC"],
    }
    assert _pergunta_bate(_norm("quero me matricular no TCC"), entrada)


def test_pergunta_bate_por_todas_as_palavras_chave():
    entrada = {"palavras_chave": ["estagio", "carga horaria"]}
    assert _pergunta_bate(_norm("qual a carga horária do estágio?"), entrada)


def test_pergunta_nao_bate_quando_falta_palavra_chave():
    entrada = {"palavras_chave": ["estagio", "carga horaria"]}
    assert not _pergunta_bate(_norm("qual a carga horária do TCC?"), entrada)


def test_pergunta_nao_bate_sem_candidatos():
    assert not _pergunta_bate(_norm("pergunta qualquer"), {})


def test_resposta_literal_cita_fonte_quando_presente():
    entrada = {"resposta_literal": "O prazo é de 30 dias.", "fonte_documento": "Resolucao_TCC.pdf"}
    assert _resposta_literal(entrada) == "O prazo é de 30 dias.\n\nFonte: Resolucao_TCC.pdf"


def test_resposta_literal_sem_fonte():
    entrada = {"resposta_literal": "O prazo é de 30 dias."}
    assert _resposta_literal(entrada) == "O prazo é de 30 dias."


def test_resposta_literal_none_quando_vazia():
    assert _resposta_literal({}) is None
