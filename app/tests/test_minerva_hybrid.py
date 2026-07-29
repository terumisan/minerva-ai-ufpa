from minerva_hybrid import (
    _chunk_bate_multiplos_termos,
    _expandir_termo,
    _fusao_rrf,
    _grupo_tsquery,
    _termos_relevantes,
    fallback_sem_base,
    sanitizar_resposta,
)


def test_sanitizar_resposta_vazia_usa_fallback():
    assert sanitizar_resposta("") == fallback_sem_base()
    assert sanitizar_resposta(None) == fallback_sem_base()


def test_sanitizar_resposta_bloqueia_instituicao_externa_por_frase():
    resposta = sanitizar_resposta("A FCT fica na Universidade Federal de Pernambuco.")
    assert "Referência correta" in resposta
    assert "Pernambuco" not in resposta.split("Referência")[0]


def test_sanitizar_resposta_bloqueia_sigla_externa_com_limite_de_palavra():
    resposta = sanitizar_resposta("Consulte também a UFPE para mais detalhes.")
    assert "Referência correta" in resposta


def test_sanitizar_resposta_nao_bloqueia_falso_positivo_de_substring():
    # "upe" não pode disparar em palavras comuns que o contêm.
    resposta = sanitizar_resposta("O supervisor de estágio deve assinar o termo.")
    assert resposta == "O supervisor de estágio deve assinar o termo."


def test_sanitizar_resposta_bloqueia_universidade_nova_de_lisboa_isolada():
    # Bug real: antes dessa entrada, só a frase exata "Faculdade de Ciências
    # e Tecnologia" era bloqueada — "Universidade Nova de Lisboa" sozinha
    # (sem repetir aquele nome) passava direto, mesmo sendo a mesma confusão
    # FCT/UFPA x FCT/Portugal.
    resposta = sanitizar_resposta("Trata-se da Universidade Nova de Lisboa, em Portugal.")
    assert "Referência correta" in resposta


def test_sanitizar_resposta_bloqueia_fct_de_portugal_sem_nome_completo():
    resposta = sanitizar_resposta("A FCT de Portugal fica em Lisboa.")
    assert "Referência correta" in resposta


def test_sanitizar_resposta_bloqueia_fct_unl():
    resposta = sanitizar_resposta("A FCT-UNL é uma faculdade portuguesa.")
    assert "Referência correta" in resposta


def test_sanitizar_resposta_nao_bloqueia_fct_sem_portugal():
    resposta = "A FCT é a Faculdade de Computação e Telecomunicações da UFPA."
    assert sanitizar_resposta(resposta) == resposta


def test_sanitizar_resposta_ok_passa_direto():
    texto = "O trancamento de matrícula segue o Regulamento de Graduação."
    assert sanitizar_resposta(texto) == texto


def test_expandir_termo_sinonimos_institucionais():
    grupo = _expandir_termo("trancar")
    assert "cancelamento" in grupo
    assert "suspensao" in grupo


def test_expandir_termo_sem_sinonimo_retorna_proprio_termo():
    assert _expandir_termo("xyz123") == {"xyz123"}


def test_grupo_tsquery_termo_unico():
    assert _grupo_tsquery("xyz123") == "xyz123:*"


def test_grupo_tsquery_grupo_com_sinonimos_usa_or():
    query = _grupo_tsquery("tcc")
    assert query.startswith("(")
    assert "tcc:*" in query
    assert "monografia:*" in query
    assert "|" in query


def test_termos_relevantes_remove_stopwords_e_curtas():
    # _termos_relevantes não remove acentos (isso é feito por _sem_acento,
    # usado só na expansão de sinônimos) — mantém "matrícula" acentuada.
    termos = _termos_relevantes("Como faço para trancar a matrícula?")
    assert "trancar" in termos
    assert "matrícula" in termos
    assert "para" not in termos
    assert "a" not in termos


def test_termos_relevantes_fallback_quando_so_ha_stopwords():
    termos = _termos_relevantes("Onde? Quando?")
    assert termos  # não pode ficar vazio, senão a busca lexica nunca dispara


def test_fusao_rrf_prioriza_item_bem_ranqueado_nas_duas_listas():
    lexica = [
        {"id": 1, "titulo": "A", "trecho": "trecho A"},
        {"id": 2, "titulo": "B", "trecho": "trecho B"},
    ]
    semantica = [
        {"id": 2, "titulo": "B", "trecho": "trecho B"},
        {"id": 3, "titulo": "C", "trecho": "trecho C"},
    ]

    resultado = _fusao_rrf(lexica, semantica, limite=3)

    assert resultado[0]["titulo"] == "B"
    assert len(resultado) == 3


def test_fusao_rrf_listas_vazias():
    assert _fusao_rrf([], [], limite=5) == []


# ----------------------------------------------------------------------
# Filtro de relevância do fallback OU da busca léxica
# ----------------------------------------------------------------------

def test_chunk_bate_multiplos_termos_exige_dois_termos_no_fallback_or():
    # Bug real: "Quem foi Dom Pedro I do Brasil?" (termos relevantes:
    # foi, dom, pedro, brasil) casava com QUALQUER chunk institucional
    # que só contivesse "Brasil" em algum lugar — palavra genérica demais
    # para ser sinal de relevância sozinha.
    termos = ["foi", "dom", "pedro", "brasil"]
    trecho_so_brasil = "Universidade Federal do Pará, Brasil, campus Belém."
    assert not _chunk_bate_multiplos_termos(trecho_so_brasil, termos)

    trecho_dois_termos = "Dom Pedro foi imperador do Brasil em 1822."
    assert _chunk_bate_multiplos_termos(trecho_dois_termos, termos)


def test_chunk_bate_multiplos_termos_um_termo_so_sempre_passa():
    # Pergunta com um único termo relevante ("trancamento?") não tem como
    # exigir 2 — a checagem vira permissiva de propósito nesse caso.
    assert _chunk_bate_multiplos_termos("texto sobre trancamento de matricula", ["trancamento"])


def test_chunk_bate_multiplos_termos_usa_sinonimos():
    # "cancelar" é sinônimo de "trancar" (SINONIMOS_INSTITUCIONAIS) — o
    # trecho não precisa repetir a palavra exata da pergunta.
    termos = ["cancelar", "matricula"]
    trecho = "O discente pode requerer o trancamento de sua matrícula."
    assert _chunk_bate_multiplos_termos(trecho, termos)
