"""Cache em memória de respostas do RAG para perguntas repetidas.

Só guarda respostas bem-sucedidas do caminho documental (não fallbacks nem
erros) e as invalida sozinho quando muda o catálogo (minerva_dataset.json) ou o
corpus de PDFs (manifesto no PostgreSQL). Vive no processo da UI: reiniciar o
container limpa o cache. Não guarda identificação de usuário, só pergunta
normalizada e resposta.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

try:
    from .minerva_dataset import DATASET_PATH, _norm
except (ImportError, ValueError):
    from minerva_dataset import DATASET_PATH, _norm

CAPACIDADE = int(os.getenv("MINERVA_CACHE_CAPACIDADE", "256"))
TTL_SEGUNDOS = int(os.getenv("MINERVA_CACHE_TTL", str(12 * 3600)))


class CacheRespostas:
    def __init__(self, capacidade: int = CAPACIDADE, ttl: float = TTL_SEGUNDOS,
                 relogio: Callable[[], float] = time.monotonic):
        self.capacidade = capacidade
        self.ttl = ttl
        self._relogio = relogio
        self._itens: OrderedDict[tuple[str, str], tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def chave(pergunta: str, versao: str) -> tuple[str, str]:
        return _norm(pergunta), versao

    def obter(self, pergunta: str, versao: str) -> Optional[str]:
        if self.capacidade <= 0 or not versao:
            return None
        k = self.chave(pergunta, versao)
        with self._lock:
            item = self._itens.get(k)
            if item is None:
                return None
            criado, resposta = item
            if self._relogio() - criado > self.ttl:
                del self._itens[k]
                return None
            self._itens.move_to_end(k)
            return resposta

    def guardar(self, pergunta: str, versao: str, resposta: str) -> None:
        if self.capacidade <= 0 or not versao or not _norm(pergunta):
            return
        k = self.chave(pergunta, versao)
        with self._lock:
            self._itens[k] = (self._relogio(), resposta)
            self._itens.move_to_end(k)
            while len(self._itens) > self.capacidade:
                self._itens.popitem(last=False)

    def __len__(self) -> int:
        return len(self._itens)


CACHE = CacheRespostas()


def versao_base(conn, dataset_path: Path = DATASET_PATH) -> str:
    """Assinatura do catálogo + corpus. Vazia (sem cache) se não der para ler."""
    try:
        st = Path(dataset_path).stat()
        partes = [f"dataset:{st.st_mtime_ns}:{st.st_size}"]
    except OSError:
        return ""
    if conn is None:
        return ""
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT coalesce(string_agg(nome_arquivo || ':' || sha256 || ':' ||
                embedding_config || ':' || chunks, ',' ORDER BY nome_arquivo), '')
                FROM minerva_documentos_manifesto""")
            partes.append("corpus:" + (cur.fetchone()[0] or ""))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return ""
    return hashlib.sha256("|".join(partes).encode()).hexdigest()


def resposta_cacheavel(resposta, falhas: tuple[str, ...]) -> bool:
    """Só respostas documentais completas; nunca fallback ou degradação."""
    if not isinstance(resposta, str) or not resposta.strip():
        return False
    return not any(resposta.startswith(f) for f in falhas)
