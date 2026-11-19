"""Mostra, passo a passo, por que o RAG genérico respondeu como respondeu.

Uso: docker exec ufpa_rag_ui python scripts/diagnosticar_pergunta.py "pergunta"
"""
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import minerva_hybrid as rag  # noqa: E402
from minerva_normas import consulta_normativa, evidencia_suficiente_para_abandono  # noqa: E402
from prompts import consultar_modelo_local  # noqa: E402
from scripts.ingestao import conectar_banco  # noqa: E402

pergunta = " ".join(sys.argv[1:])
saidas = []


def llm(prompt, max_tokens=None):
    r = consultar_modelo_local(prompt) if max_tokens is None else consultar_modelo_local(prompt, max_tokens=max_tokens)
    saidas.append(r)
    return r


with closing(conectar_banco()) as conn:
    fontes = list(rag._evidencias_rastreaveis(rag.buscar_em_documentos_postgres(conn, pergunta)).values())
    print(f"PERGUNTA: {pergunta}\n\n1. Trechos recuperados ({len(fontes)}):")
    for f in fontes:
        print(f"   [T:{f['id']}] {f['titulo']} p.{f.get('pagina_inicio')}: {f['trecho'][:110]!r}")
    print(f"\n2. Entrada contextual do catálogo: {rag._entrada_contextual(pergunta) is not None}")
    print(f"3. Evidência suficiente: {evidencia_suficiente_para_abandono(pergunta, fontes)}")
    print(f"4. Consulta normativa (só excertos): {consulta_normativa(pergunta)}")
    resposta = rag.responder_minerva(pergunta, conn=conn, llm_func=llm)
    for i, s in enumerate(saidas, 1):
        print(f"\n5.{i} Saída bruta do modelo:\n{s}")
        if s:
            print(f"   citações válidas: {rag.validar_referencias(s, fontes)} | "
                  f"prosa sem citação: {rag._prosa_sem_citacao(s)}")
    print(f"\n6. RESPOSTA FINAL:\n{resposta[:700]}")
