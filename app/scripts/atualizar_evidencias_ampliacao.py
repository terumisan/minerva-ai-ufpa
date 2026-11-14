"""Recalcula as evidências de página das entradas de ampliação documental.

As entradas com origem_entrada.tipo == "ampliacao_documental" foram redigidas
fora do container; o texto de cada página precisa ser idêntico ao extraído pela
mesma versão do pypdf usada por sincronizar_qa.py. Este script:

  1. confere o SHA-256 de cada PDF citado (aborta se o PDF mudou);
  2. regrava texto e texto_sha256 das páginas indicadas, só nessas entradas;
  3. não altera perguntas, respostas, relações nem entradas antigas;
  4. não aprova respostas literais (autorizacao_literal continua "pendente").

Uso (dentro do container):
  docker compose exec -T ufpa_rag_ui python scripts/atualizar_evidencias_ampliacao.py
  docker compose exec -T ufpa_rag_ui python scripts/sincronizar_qa.py
"""
import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path,
                   default=Path(__file__).resolve().parents[1] / "minerva_dataset.json")
    p.add_argument("--documentos", type=Path, default=Path("/documentos"))
    args = p.parse_args()

    dados = json.loads(args.dataset.read_text(encoding="utf-8"))
    cache, alteradas, total = {}, 0, 0
    for e in dados["respostas_especificas"]:
        if (e.get("origem_entrada") or {}).get("tipo") != "ampliacao_documental":
            continue
        c = e["contexto_documental"]
        nome = c["documento"]
        if Path(nome).name != nome:
            raise ValueError(f"Nome de documento inválido: {nome}")
        if nome not in cache:
            path = args.documentos / nome
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            paginas = [" ".join((pg.extract_text() or "").split()) for pg in PdfReader(path).pages]
            cache[nome] = digest, paginas
        digest, paginas = cache[nome]
        if digest != c["documento_sha256"]:
            raise ValueError(f"PDF diferente do usado na redação ({e['id']}): {nome}")
        for v in c["evidencias"]:
            n = v["pagina_fisica"]
            if n < 1 or n > len(paginas) or not paginas[n - 1]:
                raise ValueError(f"Página sem texto ({e['id']}): {nome}, {n}")
            total += 1
            texto = paginas[n - 1]
            if v["texto"] != texto:
                v["texto"] = texto
                v["texto_sha256"] = hashlib.sha256(texto.encode()).hexdigest()
                alteradas += 1

    args.dataset.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidencias_verificadas": total, "evidencias_atualizadas": alteradas},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
