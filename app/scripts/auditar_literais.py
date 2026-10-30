"""Inventário de autorizações locais; não aprova conteúdo institucional."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minerva_dataset import _carregar_entradas  # noqa: E402
from minerva_static import snapshot_verificado  # noqa: E402


def auditar():
    entradas = [e for e in _carregar_entradas() if e.get("estrategia_recuperacao") in ("RESPOSTA_LITERAL", "STATIC_VERIFIED")]
    aprovadas = [e["id"] for e in entradas if snapshot_verificado(e)]
    return {"literais": len(entradas), "autorizadas": aprovadas,
            "pendentes": [e["id"] for e in entradas if e["id"] not in aprovadas],
            "limite": "Não cobre auditoria editorial das rotas fixas/basic_facts nem verifica vigência online"}


if __name__ == "__main__":
    print(json.dumps(auditar(), ensure_ascii=False, indent=2))
