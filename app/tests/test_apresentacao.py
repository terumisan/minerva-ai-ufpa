import pytest

from minerva_apresentacao import escapar_markdown, separar_fontes
from minerva_hybrid import _anexar_referencias


def referencia(url='https://fct.ufpa.br/norma.pdf'):
    fonte = dict(id=91, titulo='Norma.pdf', trecho='Art. 7. Exige B. Salvo mudança: A.',
                 pagina_inicio=2, pagina_fim=3, documento_sha256='a' * 64,
                 chunk_uid='b' * 64, source_url=url)
    return _anexar_referencias('Excertos para consulta.', [fonte], [91]), fonte


def test_apresentacao_preserva_excerto_e_rastreabilidade():
    resposta, fonte = referencia()
    cabecalho, fontes = separar_fontes(resposta)
    assert cabecalho == 'Excertos para consulta.'
    assert fontes[0]['trecho'] == fonte['trecho']
    assert fontes[0]['paginas'] == 'páginas físicas 2–3'
    assert fontes[0]['url'] == fonte['source_url'] + '#page=2'
    assert fonte['documento_sha256'] in fontes[0]['detalhes']
    assert fonte['chunk_uid'] in fontes[0]['detalhes']


@pytest.mark.parametrize('sufixo', ['', '\n\nReferência incompleta', '\n\n- [T:2] inválido'])
def test_formato_desconhecido_nao_perde_conteudo(sufixo):
    resposta = 'Resposta sem referências.' if not sufixo else referencia()[0] + sufixo
    assert separar_fontes(resposta) == (resposta, [])


@pytest.mark.parametrize('url', ['https://ufpa.br.exemplo.org/a.pdf', 'https://outro.org/a.pdf'])
def test_origem_nao_oficial_nao_vira_botao(url):
    resposta, _ = referencia(url)
    _, fontes = separar_fontes(resposta)
    assert fontes[0]['url'] is None
    assert url in fontes[0]['detalhes']


def test_texto_documental_nao_ganha_links_ou_formatacao():
    texto = '[abra](https://exemplo.org) **obrigatório** <script>não executar</script>'
    escapado = escapar_markdown(texto)
    assert r'\[abra\]\(https://exemplo\.org\)' in escapado
    assert r'\*\*obrigatório\*\*' in escapado
    assert r'\<script\>' in escapado
    # O sinal inicial também é escapado; não vira citação Markdown.
    assert escapar_markdown('> citação') == r'\> citação'
