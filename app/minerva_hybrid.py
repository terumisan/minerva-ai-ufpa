import re
import unicodedata

# Frases longas: seguras como substring simples (não têm risco de dar falso
# positivo dentro de outra palavra).
TERMOS_BLOQUEADOS_FRASES = [
    "universidade federal de pernambuco",
    "universidade federal da paraíba",
    "universidade federal da paraiba",
    "universidade de pernambuco",
    "faculdade de ciências técnicas",
    "faculdade de ciencias tecnicas",
    # Confirmado na prática com o Gemma 4: sem grounding, o modelo confunde
    # a FCT/UFPA com a Faculdade de Ciências e Tecnologia da Universidade
    # Nova de Lisboa (também conhecida como "FCT" em Portugal).
    "faculdade de ciências e tecnologia",
    "faculdade de ciencias e tecnologia",
]

# Siglas curtas: precisam de limite de palavra (\b), senão "upe" também bate
# em "superior", "supervisor", "ocupem" etc. — palavras comuns em regimentos.
TERMOS_BLOQUEADOS_SIGLAS = [
    "ufpb",
    "ufpe",
    "upe",
]

def fallback_sem_base():
    return (
        "Não localizei informação institucional suficiente na base disponível "
        "da FCT/UFPA para responder com segurança."
    )

def sanitizar_resposta(resposta):
    if not resposta:
        return fallback_sem_base()

    baixo = resposta.lower()

    bloqueado = any(
        frase in baixo for frase in TERMOS_BLOQUEADOS_FRASES
    ) or any(
        re.search(rf"\b{re.escape(sigla)}\b", baixo)
        for sigla in TERMOS_BLOQUEADOS_SIGLAS
    )

    if bloqueado:
        return (
            "Não localizei informação institucional segura na base da FCT/UFPA "
            "para responder sem risco de erro.\n\n"
            "**Referência correta:**\n"
            "- **FCT:** Faculdade de Computação e Telecomunicações\n"
            "- **UFPA:** Universidade Federal do Pará"
        )

    return resposta

_STOPWORDS_BUSCA = {
    "que", "para", "com", "sem", "uma", "umas", "uns", "das", "dos", "por",
    "como", "mais", "menos", "isso", "essa", "esse", "esta", "este", "sao",
    "tem", "ter", "ser", "onde", "quando", "quem", "qual", "quais", "nas",
    "nos", "num", "numa", "ate", "apos", "sobre", "entre", "pelo", "pela",
}


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Sinônimos institucionais: a busca léxica (tsvector) só encontra chunks que
# compartilham RADICAL de palavra com a pergunta — "cancelar matrícula" nunca
# batia com um trecho que só tem "trancamento", mesmo sendo o mesmo assunto.
# Cada grupo é tratado como equivalente na hora de montar o tsquery (OR entre
# os termos do grupo). Chaves/valores sem acento (comparação normalizada).
SINONIMOS_INSTITUCIONAIS: dict[str, list[str]] = {
    "trancar": ["trancamento", "cancelar", "cancelamento", "suspender", "suspensao"],
    "tcc": ["monografia", "conclusao"],
    "estagio": ["estagiario", "estagiaria"],
    "matricula": ["inscricao", "matricular", "rematricula"],
    "disciplina": ["materia", "componente"],
    "professor": ["docente", "professores", "docentes"],
    "aluno": ["discente", "estudante", "alunos", "discentes"],
    "nota": ["conceito", "avaliacao"],
    "reprovar": ["reprovacao", "reprovado"],
    "aproveitamento": ["equivalencia", "dispensa"],
    "diploma": ["certificado", "colacao"],
    "bolsa": ["bolsista", "auxilio"],
}

_GRUPOS_SINONIMOS: list[set[str]] = [
    {_sem_acento(chave)} | {_sem_acento(v) for v in variantes}
    for chave, variantes in SINONIMOS_INSTITUCIONAIS.items()
]


def _expandir_termo(termo: str) -> set[str]:
    termo_norm = _sem_acento(termo)

    for grupo in _GRUPOS_SINONIMOS:
        if termo_norm in grupo:
            return grupo

    return {termo}


def _termos_relevantes(pergunta: str) -> list[str]:
    """Extrai os termos de conteúdo da pergunta (sem stopwords/palavras curtas)."""
    todas_palavras = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", pergunta.lower())

    termos = [
        palavra
        for palavra in todas_palavras
        if len(palavra) > 2 and palavra not in _STOPWORDS_BUSCA
    ]

    # Fallback quando a pergunta é só stopwords/palavras curtas ("Onde? Quando?").
    return termos or todas_palavras


def _grupo_tsquery(termo: str) -> str:
    """':*' (prefixo): o stemmer 'portuguese' reduz "trancar" a 'tranc' e
    "trancamento" a 'trancament' — lexemas DIFERENTES apesar de serem a mesma
    família de palavra. "tranc:*" casa com qualquer lexema começando por
    "tranc", cobrindo variações morfológicas. Cada termo também expande para
    seu grupo de sinônimos (ver SINONIMOS_INSTITUCIONAIS).
    """
    grupo = sorted(_expandir_termo(termo))
    partes = [f"{t}:*" for t in grupo]

    if len(partes) == 1:
        return partes[0]

    return "(" + " | ".join(partes) + ")"


# ----------------------------------------------------------------------
# Embedding semântico (fastembed, ONNX — sem depender de torch/GPU).
# Mesmo modelo usado em app/scripts/ingestao.py: embeddings de pergunta e de
# chunk precisam vir do mesmo modelo para a distância de cosseno fazer
# sentido. Carregado uma única vez por processo (~450ms depois de baixado
# e cacheado) e nunca recarregado — se falhar, a busca léxica sozinha ainda
# funciona (degradação graciosa, não é um requisito rígido).
# ----------------------------------------------------------------------
_EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_EMBEDDING_CACHE_DIR = "/app/.fastembed_cache"

_embedding_model = None
_embedding_model_falhou = False


def _get_embedding_model():
    global _embedding_model, _embedding_model_falhou

    if _embedding_model is not None:
        return _embedding_model

    if _embedding_model_falhou:
        return None

    try:
        from fastembed import TextEmbedding

        _embedding_model = TextEmbedding(
            model_name=_EMBEDDING_MODEL_NAME,
            cache_dir=_EMBEDDING_CACHE_DIR,
        )
    except Exception:
        _embedding_model_falhou = True
        _embedding_model = None

    return _embedding_model


def _buscar_lexico(conn, pergunta, limite=10):
    termos = _termos_relevantes(pergunta)

    if not termos:
        return []

    sql = """
        SELECT
            id,
            nome_arquivo AS titulo,
            LEFT(conteudo, 2500) AS trecho
        FROM documentos_ufpa
        WHERE
            to_tsvector('portuguese', conteudo) @@ to_tsquery('portuguese', %s)
        ORDER BY
            ts_rank_cd(to_tsvector('portuguese', conteudo), to_tsquery('portuguese', %s)) DESC
        LIMIT %s
    """

    # Bug real (histórico): OR puro entre todos os termos ("trancar | curso")
    # deixava uma palavra genérica e frequente ("curso", presente em quase
    # todo chunk institucional) dominar o ranking sobre o termo raro e
    # realmente relevante ("trancar"/"trancamento"). Estratégia: tentar E
    # lógico (todos os termos, mais preciso) primeiro; só cair para OU (mais
    # abrangente) se a busca com E não achar nada.
    tsquery_grupos = [_grupo_tsquery(termo) for termo in termos]
    tsquery_and = " & ".join(tsquery_grupos)
    tsquery_or = " | ".join(tsquery_grupos)

    for tsquery_texto in (tsquery_and, tsquery_or) if tsquery_and != tsquery_or else (tsquery_and,):
        try:
            cur = conn.cursor()
            cur.execute(sql, (tsquery_texto, tsquery_texto, limite))
            rows = cur.fetchall()
            cur.close()
        except Exception:
            try:
                cur.close()
            except Exception:
                pass
            rows = []

        if rows:
            return [
                {"id": r[0], "titulo": r[1], "trecho": r[2]}
                for r in rows
                if r and len(r) >= 3 and r[2]
            ]

    return []


def _buscar_semantico(conn, pergunta, limite=10):
    modelo = _get_embedding_model()

    if modelo is None:
        return []

    try:
        vetor = list(modelo.embed([pergunta]))[0]
        vetor_literal = "[" + ",".join(f"{v:.6f}" for v in vetor.tolist()) + "]"
    except Exception:
        return []

    sql = """
        SELECT
            id,
            nome_arquivo AS titulo,
            LEFT(conteudo, 2500) AS trecho
        FROM documentos_ufpa
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    try:
        cur = conn.cursor()
        cur.execute(sql, (vetor_literal, limite))
        rows = cur.fetchall()
        cur.close()
    except Exception:
        try:
            cur.close()
        except Exception:
            pass
        return []

    return [
        {"id": r[0], "titulo": r[1], "trecho": r[2]}
        for r in rows
        if r and len(r) >= 3 and r[2]
    ]


def _fusao_rrf(lista_lexica, lista_semantica, k=60, limite=5):
    """Reciprocal Rank Fusion: combina o ranking léxico (tsvector/ts_rank_cd)
    com o semântico (cosseno de embedding) num único ranking, sem precisar
    calibrar pesos entre duas escalas de score que não são comparáveis entre
    si (ts_rank_cd não é a mesma unidade que similaridade de cosseno). Um
    chunk que aparece bem posicionado nas duas listas sobe no ranking final;
    um chunk que só aparece numa delas ainda concorre, só que com peso menor.
    """
    scores: dict[int, float] = {}
    dados: dict[int, dict] = {}

    for lista in (lista_lexica, lista_semantica):
        for rank, item in enumerate(lista):
            chave = item["id"]
            scores[chave] = scores.get(chave, 0.0) + 1.0 / (k + rank + 1)
            dados[chave] = item

    ordenado = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    return [
        {
            "titulo": dados[chave]["titulo"],
            "trecho": dados[chave]["trecho"],
            "fonte": "Base documental local",
        }
        for chave, _ in ordenado[:limite]
    ]


def buscar_em_documentos_postgres(conn, pergunta, limite=6):
    # limite=6 (não 5): com a fusão RRF, um chunk correto mas ranqueado só em
    # 4º/5º lugar na lista semântica (paráfrases mais abstratas, ex. "desistir
    # do curso por um tempo" para "trancamento de matrícula") ainda precisa
    # de espaço para entrar no resultado final. Testado com 8: a latência em
    # CPU quase triplicou (70s -> ~190s) para ganho de recall inconsistente
    # nos casos mais difíceis — 6 é o meio-termo entre dar mais chance a
    # candidatos semânticos fracos e não sobrecarregar o modelo (3B, CPU)
    # com trechos de assuntos diferentes que ele pode acabar misturando.
    if conn is None:
        return []

    # Schema real (ver app/scripts/ingestao.py): id, nome_arquivo, conteudo,
    # embedding. Consultas antigas aqui referenciavam colunas inexistentes
    # (titulo, texto, texto_extraido), o que derrubava a query com "column
    # does not exist" e fazia esta função sempre devolver [] silenciosamente.
    lista_lexica = _buscar_lexico(conn, pergunta, limite=10)
    lista_semantica = _buscar_semantico(conn, pergunta, limite=10)

    if not lista_lexica and not lista_semantica:
        return []

    return _fusao_rrf(lista_lexica, lista_semantica, limite=limite)

def resposta_extrativa(fontes):
    if not fontes:
        return fallback_sem_base()

    partes = ["Com base nas fontes institucionais disponíveis da FCT/UFPA:\n"]

    for f in fontes[:3]:
        titulo = f.get("titulo", "Fonte institucional")
        trecho = f.get("trecho", "").strip()

        if trecho:
            partes.append(f"**{titulo}**\n{trecho[:900]}...")

    partes.append(
        "\nA resposta foi limitada ao conteúdo encontrado na base institucional disponível."
    )

    return sanitizar_resposta("\n\n".join(partes))

def responder_minerva(pergunta, conn=None, llm_func=None):
    fontes = buscar_em_documentos_postgres(conn, pergunta)

    contexto = "\n\n".join(
        f"Fonte: {f['titulo']}\nTrecho: {f['trecho']}"
        for f in fontes
    )

    if llm_func and contexto:
        prompt = f"""
Você é a Minerva, assistente acadêmica da Faculdade de Computação e Telecomunicações da Universidade Federal do Pará.

Regras obrigatórias:
- FCT significa Faculdade de Computação e Telecomunicações.
- UFPA significa Universidade Federal do Pará.
- Nunca use UFPB, UFPE, UPE ou outras universidades como se fossem UFPA.
- Não invente informações.
- Responda somente com base no contexto abaixo.
- O contexto vem de uma busca automática: pode incluir, junto com o(s) trecho(s)
  realmente relevante(s), outros trechos de assuntos diferentes. Use o(s)
  trecho(s) que respondem à pergunta normalmente, citando-o(s). Não misture
  esse trecho relevante com informações de um trecho de assunto diferente
  para compor um procedimento que nenhum dos dois descreve sozinho.

Pergunta:
{pergunta}

Contexto institucional:
{contexto}
"""
        try:
            resposta = llm_func(prompt)
            return sanitizar_resposta(resposta)
        except Exception:
            pass

    return resposta_extrativa(fontes)
