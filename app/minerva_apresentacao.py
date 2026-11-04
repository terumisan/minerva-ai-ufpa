"""Organiza referências já anexadas pela aplicação; não valida conteúdo factual."""
import re
from urllib.parse import urldefrag
from urllib.error import URLError

from web_segura import validar_url


def escapar_markdown(texto):
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~])", r"\\\1", texto)


def separar_fontes(resposta):
    """Só separa o formato completo conhecido; formato antigo permanece íntegro."""
    cabecalho, separador, corpo = resposta.partition('\n\n**Trechos citados:**\n\n')
    if not separador:
        return resposta, []
    fontes = []
    for bloco in corpo.split('\n\n'):
        match = re.fullmatch(
            r'- \[T:([1-9][0-9]*)\] Documento: `([^`\n]+)`(.*?) — trecho: `([^`\n]+)`',
            bloco,
        )
        if not match:
            return resposta, []
        chave, titulo, detalhes, trecho = match.groups()
        pagina = re.search(r' — (páginas? físicas? [0-9]+(?:–[0-9]+)?)', detalhes)
        origem = re.search(r' — origem: (https://\S+)$', detalhes)
        url = origem.group(1) if origem else None
        if url:
            try:
                validar_url(url)
            except URLError:
                url = None
        if url and pagina:
            numero = re.search(r'[0-9]+', pagina.group(1)).group()
            url = f'{urldefrag(url)[0]}#page={numero}'
        fontes.append(dict(id=chave, titulo=titulo, paginas=pagina.group(1) if pagina else '',
                           trecho=trecho, url=url, detalhes=bloco))
    return cabecalho.rstrip(), fontes
