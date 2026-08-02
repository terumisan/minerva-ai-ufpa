from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

# Reaproveita o que já existe em minerva_basic_facts.py em vez de duplicar
# fetch/parsing: BASIC_FACTS para respostas já conhecidas, _fetch/
# _official_ufpa_url para a busca controlada em domínios *.ufpa.br.
try:
    from .minerva_basic_facts import BASIC_FACTS, _fetch, _official_ufpa_url
except (ImportError, ValueError):
    from minerva_basic_facts import BASIC_FACTS, _fetch, _official_ufpa_url


# ======================================================================
# MINERVA AI
# Dataset de respostas específicas (perguntas cadastradas manualmente).
#
# Formato de cada entrada em minerva_dataset.json: id, macroarea, intent,
# pergunta, variacoes, entidades, palavras_chave, url_oficial,
# estrategia_recuperacao, prioridade, ativo, etc.
#
# estrategia_recuperacao == "RESPOSTA_LITERAL": além dos campos acima, usa
# resposta_literal (texto fixo, extraído de um documento já ingerido) e
# fonte_documento (nome do PDF, citado ao final da resposta). Ver
# _resposta_literal() abaixo e app/scripts/promover_eval_dataset.py.
#
# Prioridade "Baixa" por padrão: este dataset só entra como último recurso,
# depois de todo o roteamento fixo já existente (minerva_priority_router +
# minerva_basic_facts). Entradas aqui não substituem uma rota já correta —
# preenchem lacunas que ainda não têm rota dedicada.
# ======================================================================


DATASET_PATH = Path(__file__).resolve().parent / "minerva_dataset.json"

_ORDEM_PRIORIDADE = {
    "alta": 0,
    "media": 1,
    "média": 1,
    "baixa": 2,
}


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _carregar_entradas() -> list[dict]:
    try:
        dados = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entradas = dados.get("respostas_especificas", [])

    return sorted(
        entradas,
        key=lambda e: _ORDEM_PRIORIDADE.get(_norm(e.get("prioridade", "baixa")), 2),
    )


def _pergunta_bate(pergunta_norm: str, entrada: dict) -> bool:
    candidatos = [entrada.get("pergunta", "")] + list(entrada.get("variacoes", []))

    if any(_norm(c) == pergunta_norm for c in candidatos if c):
        return True

    palavras_chave = [_norm(p) for p in entrada.get("palavras_chave", []) if p]

    return bool(palavras_chave) and all(p in pergunta_norm for p in palavras_chave)


def _resposta_conhecida(entrada: dict) -> Optional[str]:
    """Reaproveita BASIC_FACTS quando a entidade já é conhecida."""
    for entidade in entrada.get("entidades", []):
        fato = BASIC_FACTS.get(str(entidade).upper())

        if not fato:
            continue

        nome = str(fato.get("name", "")).strip()
        descricao = str(fato.get("description", "")).strip()
        fontes = [str(s) for s in fato.get("sources", [])]

        if not nome:
            continue

        resposta = f"{entidade.upper()} significa {nome}."

        if descricao:
            resposta += f" No contexto da UFPA, trata-se de {descricao}."

        if fontes:
            resposta += " Fonte oficial: " + " | ".join(fontes[:2])

        return resposta

    return None


def _resposta_literal(entrada: dict) -> Optional[str]:
    """RESPOSTA_LITERAL: resposta fixa extraída de um documento oficial já
    ingerido (ver app/scripts/gerar_eval_dataset.py + promocao_eval_dataset.py),
    para perguntas de alto valor que o RAG genérico já demonstrou responder
    bem, mas que valem a pena responder sem esperar o LLM local (2-5min/CPU).
    """
    resposta = str(entrada.get("resposta_literal", "")).strip()

    if not resposta:
        return None

    fonte = str(entrada.get("fonte_documento", "")).strip()

    if fonte:
        resposta += f"\n\nFonte: {fonte}"

    return resposta


def _resposta_via_fetch(entrada: dict) -> Optional[str]:
    """RAG_WEB_CONTROLADO: só confirma que a fonte oficial existe e cita ela.

    Não tenta sintetizar texto livre a partir do HTML aqui — extração de
    conteúdo real já é feita pelos módulos de busca dinâmica existentes
    (minerva_basic_facts/minerva_priority_router). Este fallback garante
    que, mesmo sem conteúdo próprio, a pergunta cadastrada aponte para a
    fonte oficial certa em vez de cair no "não localizei" genérico.
    """
    url = str(entrada.get("url_oficial", ""))

    if not url or not _official_ufpa_url(url):
        return None

    if not _fetch(url):
        return None

    fonte = entrada.get("fonte_esperada", "UFPA")
    pergunta = entrada.get("pergunta", "este assunto")

    return (
        f"Consulte o {fonte} para informações oficiais sobre \"{pergunta}\". "
        f"Fonte oficial: {url}"
    )


def resposta_dataset(pergunta: str) -> Optional[str]:
    if not isinstance(pergunta, str) or not pergunta.strip():
        return None

    pergunta_norm = _norm(pergunta)

    for entrada in _carregar_entradas():
        if not entrada.get("ativo", True):
            continue

        if not _pergunta_bate(pergunta_norm, entrada):
            continue

        resposta = (
            _resposta_conhecida(entrada)
            or _resposta_literal(entrada)
            or _resposta_via_fetch(entrada)
        )

        if resposta:
            return resposta

    return None


__all__ = ["resposta_dataset"]
