"""Identidade anônima e capacidade limitada, sem dependência da UI."""
import secrets
import threading
import time
from contextlib import contextmanager

MAX_PERGUNTA = 4000
INTERVALO_PERGUNTAS = 3
_vaga = threading.BoundedSemaphore(1)


def inicializar_identidade(estado, parametros):
    # A URL nunca é credencial. O identificador existe apenas no servidor,
    # durante a sessão WebSocket. Reload abre outra identidade anônima.
    parametros.pop("sid", None)
    if not estado.get("_identidade_servidor"):
        estado["session_id"] = secrets.token_urlsafe(32)
        estado["_identidade_servidor"] = True
        for chave in ("messages", "conversa_id", "ultima_requisicao"):
            estado.pop(chave, None)


def validar_pergunta(pergunta):
    if not isinstance(pergunta, str) or not pergunta.strip():
        return "Digite uma pergunta."
    if len(pergunta) > MAX_PERGUNTA:
        return f"A pergunta deve ter no máximo {MAX_PERGUNTA} caracteres."
    return None


@contextmanager
def capacidade(estado, agora=None):
    """Recusa sobrecarga imediatamente; nunca cria fila de espera ilimitada."""
    agora = time.monotonic() if agora is None else agora
    anterior = estado.get("ultima_requisicao")
    if anterior is not None and agora - anterior < INTERVALO_PERGUNTAS:
        yield "Aguarde alguns segundos antes de enviar outra pergunta."
        return
    if not _vaga.acquire(blocking=False):
        yield "A Minerva está atendendo outra consulta. Tente novamente em instantes."
        return
    estado["ultima_requisicao"] = agora
    try:
        yield None
    finally:
        _vaga.release()
