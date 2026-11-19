"""Correções do teste exploratório no site de 14/11/2026."""
import minerva_basic_facts as basic
import minerva_hybrid as hybrid
from minerva_dataset import entrada_contextual
from minerva_priority_router import priority_answer


def test_palavra_comum_apos_quem_e_nao_vira_sigla():
    # "DIRETOR" virava sigla e a busca dinâmica devolvia associação sem sentido.
    assert basic._extract_acronym("Quem é o diretor da FCT?") is None
    assert basic._extract_acronym("o que é a monitoria?") is None


def test_siglas_reais_continuam_reconhecidas():
    assert basic._extract_acronym("o que é o SIGAA?") == "SIGAA"
    assert basic._extract_acronym("o que é sigaa") == "SIGAA"
    assert basic._extract_acronym("o que significa ppc") == "PPC"
    assert basic._extract_acronym("O que é o RADIP?") == "RADIP"


def test_diretor_da_fct_vai_para_pagina_de_contato():
    resposta = priority_answer("Quem é o diretor da FCT?")
    assert resposta and "fct.ufpa.br/index.php/contato" in resposta
    assert "associação da sigla" not in resposta


def test_doenca_ou_lesao_temporaria_casa_com_entrada_do_regulamento():
    for pergunta in ("Estou com dengue, posso fazer as provas em casa?",
                     "Quebrei a perna e não consigo ir às aulas, o que faço?"):
        entrada = entrada_contextual(pergunta)
        assert entrada and entrada["id"] == "MINERVA_0218"
        assert entrada["contexto_documental"]["documento"] == "Regulamento_Graduacao.pdf"


def test_termos_de_saude_expandem_para_exercicio_domiciliar():
    for termo in ("dengue", "quebrei", "cirurgia", "casa"):
        assert "domiciliar" in hybrid._expandir_termo(termo)
    assert "domiciliar" not in hybrid._expandir_termo("matricula")


def test_variacoes_do_teste_exploratorio_casam_com_a_entrada_certa():
    assert entrada_contextual(
        "Quantas horas de atividades complementares preciso cumprir em Engenharia da Computação?"
    )["id"] == "MINERVA_0079"
    assert entrada_contextual(
        "Qual o prazo para entregar a versão final do TCC depois da defesa?"
    )["id"] == "MINERVA_0128"


def test_variacoes_do_reteste_de_15_11():
    assert entrada_contextual("Quantas vezes posso reprovar na mesma disciplina?")["id"] == "MINERVA_0097"
    assert entrada_contextual(
        "Peguei covid e o médico me deu atestado de 10 dias, posso fazer as atividades em casa?"
    )["id"] == "MINERVA_0218"


# --- 18/11/2026: rotas de "portal" só para perguntas genéricas -------------
import pytest  # noqa: E402

from minerva_priority_router import _rota_generica_nao_responde  # noqa: E402


@pytest.mark.parametrize("pergunta", [
    "quem assina como orientador na proposta de estágio?",
    "como lanço as atividades complementares no sagitta?",
    "quem avalia a progressão dos professores na faculdade?",
    "qual o email da proex?",
    "o que o diretor da faculdade tem que fiscalizar no ensino?",
])
def test_pergunta_especifica_nao_fica_na_rota_de_portal(pergunta):
    assert _rota_generica_nao_responde(pergunta)


@pytest.mark.parametrize("pergunta", [
    "o que é o estágio?",
    "Quais são as regras de estágio?",
    "como funciona o tcc?",
    "me fale sobre atividades complementares",
    "quem são os professores da fct?",
    "qual o telefone da fct?",
    "quem é o diretor da FCT?",
])
def test_pergunta_generica_continua_na_rota_de_portal(pergunta):
    assert not _rota_generica_nao_responde(pergunta)
