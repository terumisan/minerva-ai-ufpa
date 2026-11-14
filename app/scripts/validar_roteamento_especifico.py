"""Amostra operacional resumível; não homologa conteúdo nem vigência."""
import argparse
import ast
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import minerva_hybrid as rag  # noqa: E402
from minerva_dataset import entrada_contextual  # noqa: E402
from minerva_priority_router import classify_question, priority_answer  # noqa: E402
from prompts import consultar_modelo_local, pergunta_menciona_instituicao_externa  # noqa: E402
from scripts.ingestao import conectar_banco  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IDS = (70, 71, 76, 77, 79, 90)
NOVAS = (
    (70, "Para entrar no TCC I da FCT, quais disciplinas preciso ter concluído?"),
    (71, "Passei em TCC I: o que preciso entregar para me matricular no TCC II?"),
    (76, "Quero fazer estágio de 200 horas em Engenharia da Computação: quais são os requisitos?"),
    (77, "Quero fazer estágio de 390 horas em Engenharia da Computação: quais são os requisitos?"),
    (79, "Como as 120 horas de atividades complementares se dividem entre AC-I e AC-II?"),
    (90, "Só completar as horas basta para passar em AC-I e AC-II?"),
)


def executar(fase, saida):
    entradas = json.loads((ROOT / 'minerva_dataset.json').read_text())['respostas_especificas']
    por_id = {e['id']: e for e in entradas}
    casos = [(n, por_id[f'MINERVA_{n:04d}']['pergunta']) for n in IDS] if fase == 'cadastradas' else NOVAS
    feitos = {json.loads(linha)['pergunta'] for linha in saida.read_text().splitlines()} if saida.exists() else set()
    # Executa a função real da interface sem inicializar uma sessão Streamlit.
    arvore = ast.parse((ROOT / 'main.py').read_text())
    funcao = next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == '_processar_pergunta')
    conn = conectar_banco()

    class Pool:
        def getconn(self):
            return conn

        def putconn(self, connection, **kwargs):
            pass

    namespace = dict(priority_answer=priority_answer, classify_question=classify_question,
                     pergunta_menciona_instituicao_externa=pergunta_menciona_instituicao_externa,
                     db_pool=Pool(), responder_minerva=rag.responder_minerva)
    exec(compile(ast.Module(body=[funcao], type_ignores=[]), 'main.py', 'exec'), namespace)
    original = rag.buscar_em_documentos_postgres
    try:
        for numero, pergunta in casos:
            if pergunta in feitos:
                continue
            fontes, chamadas = [], []

            def buscar(*args, _fontes=fontes, **kwargs):
                resultado = original(*args, **kwargs)
                _fontes.extend(resultado)
                return resultado

            def llm(prompt, _chamadas=chamadas):
                resposta = consultar_modelo_local(prompt)
                _chamadas.append(resposta)
                return resposta

            rag.buscar_em_documentos_postgres = buscar
            namespace['consultar_modelo_local'] = llm
            inicio = time.monotonic()
            resposta, rota = namespace['_processar_pergunta'](pergunta)
            esperado = por_id[f'MINERVA_{numero:04d}']
            contexto = esperado['contexto_documental']
            pdf = Path('/documentos') / contexto['documento']
            registro = dict(pergunta=pergunta, referencia=esperado['id'], fase=fase,
                            contexto_identificado=(entrada_contextual(pergunta) or {}).get('id'),
                            contexto_esperado=contexto, rota=rota, fontes=fontes,
                            resposta=resposta, saidas_llm=chamadas,
                            pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                            segundos=round(time.monotonic()-inicio, 2))
            with saida.open('a') as arquivo:
                arquivo.write(json.dumps(registro, ensure_ascii=False)+'\n')
            print(json.dumps({k: registro[k] for k in ('referencia', 'rota', 'contexto_identificado', 'segundos')}, ensure_ascii=False), flush=True)
    finally:
        rag.buscar_em_documentos_postgres = original
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fase', choices=['cadastradas', 'novas'])
    parser.add_argument('saida', type=Path)
    args = parser.parse_args()
    executar(args.fase, args.saida)
