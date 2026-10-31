"""Promove para minerva_dataset.json (estrategia_recuperacao=RESPOSTA_LITERAL)
os itens do dataset de avaliação cuja resposta é curta/factual E cujo chunk
de origem o retrieval híbrido não encontrou bem (ver testar_retrieval.py) —
exatamente os casos em que o RAG genérico tende a falhar ou levar 2-5min
para no fim não achar o trecho certo. Perguntas bem servidas pelo RAG
genérico (retrieval encontra o chunk certo) não precisam de rota fixa.

Critério de promoção:
- retrieval não encontrou o chunk nos top-6 (posicao is None), E
- resposta_esperada é curta o bastante para ser uma resposta direta
  (heurística: < 220 caracteres) — perguntas cuja resposta é um trecho
  longo continuam melhor servidas pelo RAG (contexto, não fato pontual).

Limita a promoção (padrão 60 itens) para não inflar o dataset com entradas
de baixo valor/keywords genéricas demais que colidiriam entre si.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"
EVAL_PATH = DATA_DIR / "eval_minerva_qa.json"
RETRIEVAL_PATH = DATA_DIR / "resultado_retrieval.jsonl"
DATASET_PATH = Path(__file__).resolve().parent.parent / "minerva_dataset.json"

LIMITE_RESPOSTA_CURTA = 220
MAX_PROMOVIDOS = 60

_STOPWORDS = {
    "que", "para", "com", "sem", "uma", "umas", "uns", "das", "dos", "por",
    "como", "mais", "menos", "isso", "essa", "esse", "esta", "este", "sao",
    "tem", "ter", "ser", "onde", "quando", "quem", "qual", "quais", "nas",
    "nos", "num", "numa", "ate", "apos", "sobre", "entre", "pelo", "pela",
    "devo", "posso", "voce", "eu", "meu", "minha",
}

# Termos genéricos demais para funcionar como palavra-chave sozinhos: "o que
# ESTE documento estabelece" só faz sentido dentro do chunk de origem — fora
# dele, casa com qualquer pergunta real de aluno sobre QUALQUER documento,
# dando uma resposta fixa errada com confiança. Ver achado real: perguntas
# geradas a partir de um chunk isolado às vezes usam pronome/referência sem
# nomear o assunto (ex.: "o que esta resolução define?").
_TERMOS_GENERICOS_DEMAIS = {
    "documento", "trecho", "artigo", "texto", "resolucao", "mencionado",
    "mencionada", "regimento", "regulamento",
}


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _palavras_chave(pergunta: str, maximo: int = 4) -> list[str]:
    palavras = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", pergunta.lower())
    termos = [
        _sem_acento(p) for p in palavras
        if len(p) > 3 and _sem_acento(p) not in _STOPWORDS
    ]
    # ordem estável, sem duplicatas
    vistos = []
    for t in termos:
        if t not in vistos:
            vistos.append(t)
    return vistos[:maximo]


def main() -> None:
    if not EVAL_PATH.exists() or not RETRIEVAL_PATH.exists():
        print("Faltam eval_minerva_qa.json e/ou resultado_retrieval.jsonl — rode gerar_eval_dataset.py e testar_retrieval.py primeiro.")
        return

    eval_dados = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    perguntas = eval_dados["perguntas"]

    retrieval = [
        json.loads(linha)
        for linha in RETRIEVAL_PATH.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]

    # testar_retrieval.py itera perguntas na mesma ordem de eval_minerva_qa.json
    # e grava um resultado por pergunta (não por chunk) — um dict chaveado só
    # por chunk_id perderia uma das duas perguntas quando o mesmo chunk gera
    # dois pares (bug real: descartava candidatos válidos silenciosamente).
    if len(perguntas) != len(retrieval):
        print("AVISO: eval_minerva_qa.json e resultado_retrieval.jsonl com tamanhos diferentes — rode testar_retrieval.py de novo.")
        return

    candidatos = []
    # strict=True: o if acima já garante tamanhos iguais; falhar alto se mudar.
    for item, r in zip(perguntas, retrieval, strict=True):
        if r["encontrado"]:
            continue

        resposta = item["resposta_esperada"]
        if len(resposta) > LIMITE_RESPOSTA_CURTA:
            continue

        keywords = _palavras_chave(item["pergunta"])
        keywords_especificas = [k for k in keywords if k not in _TERMOS_GENERICOS_DEMAIS]
        if len(keywords_especificas) < 2:
            continue

        candidatos.append(item)

    # Chunks com overlap (ver ingestao.py: chunk_overlap=150) geram
    # perguntas quase idênticas a partir de trechos vizinhos — sem isso,
    # a mesma pergunta entrava duas vezes no dataset promovido.
    vistos = set()
    candidatos_unicos = []
    for c in candidatos:
        chave = _sem_acento(c["pergunta"]).lower().strip()
        if chave in vistos:
            continue
        vistos.add(chave)
        candidatos_unicos.append(c)
    candidatos = candidatos_unicos

    candidatos = candidatos[:MAX_PROMOVIDOS]

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    entradas = dataset["respostas_especificas"]
    proximo_id = max((int(e["id"].split("_")[1]) for e in entradas), default=0) + 1

    novas = []
    for item in candidatos:
        novas.append({
            "id": f"MINERVA_{proximo_id:04d}",
            "macroarea": "Promovido de avaliação (RAG com retrieval fraco)",
            "intent": "resposta_literal_promovida",
            "subintent": item["chunk_id"],
            "pergunta": item["pergunta"],
            "variacoes": [],
            "entidades": [],
            "palavras_chave": _palavras_chave(item["pergunta"]),
            "fonte_esperada": item["arquivo_fonte"],
            "url_oficial": "",
            "estrategia_recuperacao": "RESPOSTA_LITERAL",
            "resposta_literal": item["resposta_esperada"],
            "fonte_documento": item["arquivo_fonte"],
            "temporal": False,
            "prioridade": "Media",
            "tipo_resposta": "informativa",
            "resposta_esperada": item["resposta_esperada"],
            "ativo": True,
            "versao_dataset": dataset.get("versao_dataset", "1.0.0"),
        })
        proximo_id += 1

    dataset["respostas_especificas"] = entradas + novas
    DATASET_PATH.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"{len(novas)} entradas promovidas para {DATASET_PATH}")


if __name__ == "__main__":
    main()
