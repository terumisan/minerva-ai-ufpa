import json

import pytest

import minerva_hybrid as rag
from minerva_normas import consulta_normativa, evidencia_suficiente_para_abandono


@pytest.fixture
def normas():
    # Fontes sintéticas, sem transcrever respostas da avaliação de produção.
    return [
        {'id': 101, 'titulo': 'Norma.pdf', 'trecho': 'Art. 1. Compete ao colegiado aprovar projetos.'},
        {'id': 102, 'titulo': 'Norma.pdf', 'trecho': 'Art. 8. Nos cursos de especialização, compete ao colegiado supervisionar o curso.'},
        {'id': 103, 'titulo': 'Regras.pdf', 'trecho': 'Art. 3. Exige-se o formulário B. Salvo mudança de orientador: neste caso, exige-se o formulário A, assinado pelo orientador. Parágrafo único. O prazo não se aplica aos casos previstos em lei.'},
    ]


def test_norma_exibe_escopo_inteiro_sem_generalizar(monkeypatch, normas):
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    answer = rag.responder_minerva('Quais competências tem o colegiado da especialização?', llm_func=lambda p: '{"ids":[102]}')
    assert normas[1]['trecho'] in answer
    assert 'Nos cursos de especialização' in answer
    assert 'Documento: `Norma.pdf`' in answer
    assert 'conclusão sobre um caso individual' in answer
    assert '[T:101]' not in answer


def test_norma_preserva_condicoes_excecoes_e_assinatura(monkeypatch, normas):
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    answer = rag.responder_minerva('Quais documentos são obrigatórios na matrícula?', llm_func=lambda p: '{"ids":[103]}')
    assert normas[2]['trecho'] in answer
    assert 'Salvo mudança de orientador' in answer
    assert 'assinado pelo orientador' in answer
    assert 'Parágrafo único' in answer


@pytest.mark.parametrize('output', [
    'O formulário B é sempre obrigatório [T:103].',
    '{"ids":[103],"resposta":"B sempre"}',
    '{"ids":[999]}', '{"ids":[]}', '{"ids":[true]}', '{"ids":["103"]}',
])
def test_nao_publica_sintese_normativa_sem_validacao(monkeypatch, normas, output):
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    assert rag.responder_minerva('Quais são as condições de matrícula?', llm_func=lambda p: output) == rag.fallback_sem_base()


@pytest.mark.parametrize('question', [
    'O que caracteriza abandono de curso?',
    'Se eu deixar de frequentar as aulas, perco meu vínculo?',
    'Parar de estudar causa perda da vaga?',
    'Ficar sem ir às aulas configura perda de vínculo?',
])
def test_nao_equivale_ausencia_a_perda_de_vinculo(monkeypatch, question):
    fontes = [{'id': 9, 'titulo': 'Norma.pdf', 'trecho': 'O discente perderá sua vaga se não efetivar a matrícula inicial.'}]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    def llm(prompt):
        pytest.fail('Sem evidência explícita não deve chamar o LLM')
    assert rag.responder_minerva(question, llm_func=llm) == rag.fallback_sem_base()


def test_abandono_nao_implica_perda_se_efeito_so_esta_em_outro_trecho():
    fontes = [
        {'trecho': 'Abandono é uma interrupção de frequência.'},
        {'trecho': 'A perda de vaga exige processo administrativo.'},
    ]
    assert not evidencia_suficiente_para_abandono('O abandono causa perda de vaga?', fontes)


def test_evidencia_explicita_pode_ser_transcrita(monkeypatch):
    fontes = [{'id': 12, 'titulo': 'Norma.pdf', 'trecho': 'Abandono não implica perda automática do vínculo; exige análise.'}]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    answer = rag.responder_minerva('Abandono implica perda do vínculo?', llm_func=lambda p: '{"ids":[12]}')
    assert fontes[0]['trecho'] in answer


def test_sem_corte_adicional_de_excecao_apos_900_caracteres(monkeypatch):
    texto = 'Regra. ' + 'Texto da norma. ' * 90 + 'Salvo exceção: deve apresentar documento alternativo.'
    fontes = [{'id': 15, 'titulo': 'Norma.pdf', 'trecho': texto}]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    answer = rag.responder_minerva('Qual regra de matrícula?', llm_func=lambda p: '{"ids":[15]}')
    assert texto in answer
    assert texto in rag.resposta_extrativa(fontes)


def test_prompt_pede_selecao_e_nao_norma_fabricada(monkeypatch, normas):
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    def llm(prompt):
        assert 'Não confunda níveis de ensino' in prompt
        assert 'condições, exceções' in prompt
        assert normas[0]['trecho'] in prompt
        assert normas[1]['trecho'] not in prompt
        return json.dumps({'ids':[101]})
    assert '[T:101]' in rag.responder_minerva('Atribuições do colegiado?', llm_func=llm)


def test_consulta_generica_mantem_rota_anterior():
    assert not consulta_normativa('Qual é a capital?')
    assert consulta_normativa('Segundo a resolução, quais são os requisitos?')


def test_ressalva_recuperada_no_mesmo_documento_nao_e_omitida(monkeypatch):
    fontes = [
        {'id': 1, 'titulo': 'A.pdf', 'trecho': 'Art. 1. O requerimento usa formulário B.'},
        {'id': 2, 'titulo': 'A.pdf', 'trecho': 'Parágrafo único. Salvo troca de responsável, quando usa A.'},
        {'id': 3, 'titulo': 'Outro.pdf', 'trecho': 'Salvo disposição diversa, há outro prazo.'},
    ]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    answer = rag.responder_minerva('Quais condições para o requerimento?', llm_func=lambda p: '{"ids":[1]}')
    assert fontes[1]['trecho'] in answer
    assert '[T:2]' in answer
    assert '[T:3]' not in answer


def test_competencias_nao_usa_regras_de_funcionamento_ou_especializacao(monkeypatch, normas):
    normas.append({'id': 104, 'titulo': 'Norma.pdf', 'trecho': 'Art. 9. O funcionamento obedece ao regimento.'})
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    def llm(prompt):
        assert '[T:101]' in prompt
        assert '[T:102]' not in prompt
        assert '[T:104]' not in prompt
        return '{"ids":[101]}'
    answer = rag.responder_minerva('Atribuições do colegiado?', llm_func=llm)
    assert '[T:101]' in answer
    assert '[T:102]' not in answer and '[T:104]' not in answer


def test_json_cercado_com_marcador_de_id_valido(monkeypatch, normas):
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: normas)
    answer = rag.responder_minerva('Normas de matrícula?', llm_func=lambda p: '```json\n{"ids":["T:103"]}\n```')
    assert normas[2]['trecho'] in answer


def test_no_caso_nao_e_excecao_automatica(monkeypatch):
    fontes = [
        {'id': 1, 'titulo': 'A.pdf', 'trecho': 'Art. 1. Compete ao colegiado aprovar projetos.'},
        {'id': 2, 'titulo': 'A.pdf', 'trecho': 'Art. 2. A secretaria atende no caso dos pedidos comuns.'},
    ]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    answer = rag.responder_minerva('Regras do colegiado?', llm_func=lambda p: '{"ids":[1]}')
    assert '[T:2]' not in answer


def test_fonte_normativa_nao_depende_de_palavra_chave_da_pergunta(monkeypatch):
    fontes = [{'id': 1, 'titulo': 'A.pdf', 'trecho': 'Art. 1. A entrega exige assinatura, salvo dispensa expressa.'}]
    monkeypatch.setattr(rag, 'buscar_em_documentos_postgres', lambda *a: fontes)
    answer = rag.responder_minerva('Como devo proceder?', llm_func=lambda p: '{"ids":[1]}')
    assert fontes[0]['trecho'] in answer
