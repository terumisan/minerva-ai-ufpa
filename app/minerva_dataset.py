from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

try:
    from .minerva_static import snapshot_verificado
except (ImportError, ValueError):
    from minerva_static import snapshot_verificado

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

    if entrada.get("contexto_documental"):
        # Perguntas normativas contextualizadas não podem casar por palavras
        # soltas, nem confundir uma ramificação com uma paráfrase.
        return False

    palavras_chave = [_norm(p) for p in entrada.get("palavras_chave", []) if p]

    # Limites de palavra evitam colisões de substring. Exemplo real: a
    # palavra-chave "tcc i" casava dentro de "tcc ii" e fazia a pergunta
    # sobre matrícula em TCC II receber a resposta/documento de TCC I.
    def contem_termo(termo: str) -> bool:
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])",
                pergunta_norm,
            )
        )

    return bool(palavras_chave) and all(contem_termo(p) for p in palavras_chave)


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


def entrada_contextual(pergunta: str) -> Optional[dict]:
    """Identifica uma pergunta específica; nunca autoriza sua resposta fixa."""
    if not isinstance(pergunta, str) or not pergunta.strip():
        return None
    normalizada = _norm(pergunta)
    encontradas = [e for e in _carregar_entradas()
                   if e.get("ativo", True) and e.get("contexto_documental")
                   and _pergunta_bate(normalizada, e)]
    return encontradas[0] if len(encontradas) == 1 else None


def perguntas_relacionadas(pergunta: str) -> list[dict]:
    entrada = entrada_contextual(pergunta)
    if entrada is None:
        return []
    por_id = {e["id"]: e for e in _carregar_entradas()}
    resultado, vistos = [], set()
    for relacao in entrada.get("relacoes", []):
        alvo = por_id.get(relacao["id"])
        if alvo and alvo.get("entrada_canonica"):
            alvo = por_id.get(alvo["entrada_canonica"])
        if not alvo or not alvo.get("ativo", True) or alvo["id"] == entrada["id"] or alvo["id"] in vistos:
            continue
        vistos.add(alvo["id"])
        resultado.append({"id": alvo["id"], "pergunta": alvo["pergunta"],
                          "tipo": relacao["tipo"], "motivo": relacao["motivo"]})
    return resultado


def _resposta_literal(entrada: dict) -> Optional[str]:
    """Só libera texto literal com snapshot e resposta autorizados pelo curador."""
    resposta = str(entrada.get("resposta_literal", "")).strip()

    if not resposta or not snapshot_verificado(entrada):
        return None

    fonte = str(entrada.get("fonte_documento", "")).strip()

    if fonte:
        resposta += f"\n\nFonte: {fonte}"

    resposta += f"\nFonte oficial: {entrada['url_oficial']}"

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

        estrategia = entrada.get("estrategia_recuperacao")
        if estrategia in ("RESPOSTA_LITERAL", "STATIC_VERIFIED"):
            # Sem aprovação, deixa o chamador prosseguir para recuperação.
            resposta = _resposta_literal(entrada)
        elif estrategia == "RAG_WEB_CONTROLADO":
            resposta = _resposta_via_fetch(entrada)
        else:
            resposta = None

        if resposta:
            return resposta

    return None


__all__ = ["resposta_dataset"]

