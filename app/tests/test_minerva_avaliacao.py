import json

import pytest

from minerva_avaliacao import (
    ESCALA_LIKERT,
    ITENS_RAG,
    ITENS_SUS,
    _indice_likert,
    calcular_sus,
    montar_registro,
    registro_para_json,
)


def test_sus_tem_dez_itens_alternando_positivo_negativo():
    # O cálculo depende da ordem canônica do instrumento: qualquer mudança
    # na quantidade ou na alternância quebra a comparabilidade do score.
    assert len(ITENS_SUS) == 10


def test_calcular_sus_neutro_da_cinquenta():
    # Todas as respostas "3 — Neutro": ímpares contribuem 2, pares 2 -> 20 * 2,5.
    assert calcular_sus([3] * 10) == 50.0


def test_calcular_sus_maximo_da_cem():
    # Melhor cenário: concorda totalmente com as positivas (ímpares),
    # discorda totalmente das negativas (pares).
    respostas = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
    assert calcular_sus(respostas) == 100.0

def test_calcular_sus_minimo_da_zero():
    respostas = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]
    assert calcular_sus(respostas) == 0.0


def test_calcular_sus_rejeita_quantidade_errada():
    with pytest.raises(ValueError):
        calcular_sus([3] * 9)


def test_calcular_sus_rejeita_valor_fora_da_escala():
    with pytest.raises(ValueError):
        calcular_sus([3] * 9 + [6])

    with pytest.raises(ValueError):
        calcular_sus([0] + [3] * 9)


def test_indice_likert_extrai_numero_da_opcao():
    assert [_indice_likert(op) for op in ESCALA_LIKERT] == [1, 2, 3, 4, 5]


def test_montar_registro_consolida_e_pontua():
    registro = montar_registro(
        curso="Ciência da Computação",
        semestre="5",
        frequencia_ia="Uso todo dia",
        respostas_sus=[3] * 10,
        respostas_rag=[4, 4, 2, 5],
        ponto_forte="  Rotas rápidas  ",
        ponto_fraco="Latência do RAG",
        pergunta_errada="",
    )

    assert registro["sus_score"] == 50.0
    # Abertas com espaços das bordas removidos.
    assert registro["ponto_forte"] == "Rotas rápidas"
    # Itens específicos ficam associados ao texto da pergunta (legível no JSONB).
    assert registro["rag_itens"][ITENS_RAG[0]] == 4
    assert len(registro["rag_itens"]) == len(ITENS_RAG)


def test_registro_para_json_preserva_acentos():
    registro = montar_registro(
        curso="Engenharia de Telecomunicações",
        semestre="1",
        frequencia_ia="Nunca usei assistentes de IA",
        respostas_sus=[3] * 10,
        respostas_rag=[3, 3, 3, 3],
        ponto_forte="ótima",
        ponto_fraco="",
        pergunta_errada="",
    )

    texto = registro_para_json(registro)
    assert "Telecomunicações" in texto  # ensure_ascii=False
    assert json.loads(texto)["curso"] == "Engenharia de Telecomunicações"
