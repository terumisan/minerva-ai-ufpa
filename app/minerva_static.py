"""Autorização local de respostas literais; não baixa nem aprova fontes."""

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse


def snapshot_verificado(entrada: dict) -> bool:
    """Falha fechada: exige fonte UFPA, cópia íntegra e resposta aprovada.

    O manifesto é mantido pelo curador fora do código. Os hashes vinculam
    a aprovação aos bytes da fonte e ao texto exato da resposta; não atestam
    correção factual nem vigência online. Entradas temporais não são liberadas.
    """
    root_value = os.getenv("MINERVA_V7_STATIC_SNAPSHOT_DIR", "").strip()
    if not root_value or entrada.get("temporal", False) is not False:
        return False
    try:
        url = entrada.get("url_oficial", "")
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or not (host == "ufpa.br" or host.endswith(".ufpa.br"))):
            return False
        root = Path(root_value).resolve()
        manifest = json.loads((root / "static_manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return False
        entry = manifest.get(entrada.get("id"))
        if not isinstance(entry, dict) or entry.get("url") != url:
            return False
        filename = entry.get("file")
        digest = entry.get("sha256")
        answer_digest = entry.get("answer_sha256")
        if not isinstance(filename, str) or not filename:
            return False
        for value in (digest, answer_digest):
            if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value):
                return False
        answer = entrada.get("resposta_literal")
        if not isinstance(answer, str) or not answer.strip():
            return False
        source = (root / filename).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            return False
        return (
            hashlib.sha256(source.read_bytes()).hexdigest() == digest.lower()
            and hashlib.sha256(answer.strip().encode("utf-8")).hexdigest()
            == answer_digest.lower()
        )
    except (OSError, ValueError, TypeError, RuntimeError):
        return False
