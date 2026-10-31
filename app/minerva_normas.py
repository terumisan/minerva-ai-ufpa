"""Seleção conservadora de evidências normativas, sem respostas cadastradas."""
import json
import re
import unicodedata


def _normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.lower())
                   if not unicodedata.combining(c))


def consulta_normativa(pergunta):
    return bool(re.search(
        r'\b(norm\w*|regiment\w*|regulament\w*|resoluc\w*|matricul\w*|'
        r'pre.requisit\w*|condic\w*|direit\w*|obrig\w*|competenc\w*|'
        r'atribuic\w*|colegiad\w*|tcc|abandon\w*|vincul\w*|trancament\w*)\b',
        _normalizar(pergunta),
    ))


def evidencia_suficiente_para_abandono(pergunta, fontes):
    """Barreira específica de risco, não um classificador semântico completo.

    Proximidade vetorial com perda de vaga não prova regra sobre abandono.
    A ausência de menção explícita impede inferir tal relação neste contexto.
    """
    pergunta = _normalizar(pergunta)
    abandono = re.search(
        r'abandon\w*|(?:deix\w*|par\w*)\s+de\s+(?:frequent\w*|comparec\w*|ir|estud\w*)'
        r'|sem\s+(?:ir|frequent\w*|comparec\w*)\s+(?:as?\s+)?aulas', pergunta,
    )
    if not abandono:
        return True
    consequencia = bool(re.search(r'perd\w*|perco|vincul\w*|deslig\w*|vaga\w*', pergunta))
    for fonte in fontes:
        texto = _normalizar(fonte['trecho'])
        mencao = re.search(r'abandon\w*|(?:nao|deix\w*\s+de)\s+(?:frequent\w*|comparec\w*)', texto)
        efeito = re.search(r'perd\w*|vincul\w*|deslig\w*|vaga\w*', texto)
        if mencao and (not consequencia or efeito):
            return True
    return False


def selecionar_ids_normativos(texto, fontes):
    """Só aceita a seleção estruturada; nenhuma prosa do modelo vira norma."""
    if not isinstance(texto, str):
        return None
    cercado = re.fullmatch(r'\s*```(?:json)?\s*(.*?)\s*```\s*', texto, re.DOTALL)
    if cercado:
        texto = cercado.group(1)
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if not isinstance(dados, dict) or set(dados) != {'ids'}:
        return None
    ids = dados['ids']
    if not isinstance(ids, list) or not ids:
        return None
    ids = [int(i[2:]) if isinstance(i, str) and re.fullmatch(r'T:[1-9][0-9]*', i)
           else i for i in ids]
    disponiveis = {f['id'] for f in fontes}
    if any(type(i) is not int or i not in disponiveis for i in ids):
        return None
    return list(dict.fromkeys(ids))


def incluir_ressalvas_recuperadas(ids, fontes):
    """Mantém visíveis ressalvas já recuperadas do documento selecionado.

    Não afirma que sejam aplicáveis ao caso; o dispositivo e o escopo continuam
    na transcrição. Não busca nem inventa continuações ausentes do contexto.
    """
    documentos = {f['titulo'] for f in fontes if f['id'] in ids}
    resultado = list(ids)
    for fonte in fontes:
        if fonte['titulo'] in documentos and re.search(
            r'\bsalvo\b|\bexcet\w*|paragrafo unico|\bcaso\s+(?:haja|ocorra|seja|tenha)|\bexcec\w*',
            _normalizar(fonte['trecho']),
        ) and fonte['id'] not in resultado:
            resultado.append(fonte['id'])
    return resultado


def filtrar_contexto_normativo(pergunta, fontes):
    """Filtra escopos restritos não solicitados e exige pertinência ao pedido.

    Heurística conservadora: não identifica todos os níveis/intentos e pode
    abster-se de fontes relevantes. Não reescreve nem promove fatos ao dataset.
    """
    pergunta = _normalizar(pergunta)
    competencias = bool(re.search(r'competenc\w*|atribuic\w*|funco\w*', pergunta))
    resultado = []
    for fonte in fontes:
        texto = _normalizar(fonte['trecho'])
        if any(nivel in texto and nivel not in pergunta
               for nivel in ('especializacao', 'mestrado', 'doutorado')):
            continue
        if competencias and not re.search(r'\bcompete\b|atribui\w*|competenc\w*', texto):
            continue
        resultado.append(fonte)
    return resultado
