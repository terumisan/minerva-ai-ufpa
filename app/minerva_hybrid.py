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
    "universidade nova de lisboa",
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

    # "FCT" sozinha é a sigla da própria FCT/UFPA — não basta pra bloquear.
    # Associada a Portugal/Lisboa, é o mesmo caso de confusão com a FCT da
    # Universidade Nova de Lisboa, mesmo sem repetir o nome completo dela
    # (ver mesma lógica em prompts.py).
    fct_portugal = "fct" in baixo and (
        any(termo in baixo for termo in ("portugal", "português", "portugues", "lisboa"))
        or re.search(r"\bunl\b", baixo)
    )

    bloqueado = fct_portugal or any(
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
# sentido. Carregado uma única vez por processo e nunca recarregado — se
# falhar, a busca léxica sozinha ainda funciona (degradação graciosa, não é
# um requisito rígido).
#
# mpnet-base-v2 (768d, ~1GB): substituiu o MiniLM-L12 (384d, ~225MB) — ver
# justificativa e números medidos no comentário de EMBEDDING_MODEL em
# app/scripts/ingestao.py.
# ----------------------------------------------------------------------
_EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
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


def _chunk_bate_multiplos_termos(trecho: str, termos: list[str]) -> bool:
    """Exige pelo menos 2 termos distintos da pergunta (ou 1, se a
    pergunta só tinha 1 termo relevante) presentes no trecho.

    Bug real: o fallback OU do tsquery abaixo (necessário para achar
    "cancelar matrícula" quando só "trancamento" bate) também deixava
    passar chunks que só compartilham UMA palavra genérica com a
    pergunta — ex.: "Quem foi Dom Pedro I do Brasil?" casava qualquer
    chunk institucional só por conter "Brasil" em algum lugar, mesmo
    sendo um trecho sobre calendário acadêmico sem nenhuma relação com a
    pergunta. Essa checagem roda em Python (não dá pra expressar
    "N de M termos" direto num único operador tsquery) sobre os
    candidatos já trazidos pelo Postgres, sem round-trip extra.
    """
    if len(termos) <= 1:
        return True

    baixo = _sem_acento(trecho.lower())
    grupos_no_trecho = sum(
        1
        for termo in termos
        if any(
            # \b nos dois lados: sem o \b final, "dom" batia como PREFIXO
            # de "domicílio"/"domingo" (bug real, achado testando com
            # "Quem foi Dom Pedro I do Brasil?" — "dom" contava como
            # termo presente num trecho sobre mobilidade entre campi só
            # por causa de "domicílio").
            re.search(rf"\b{re.escape(variante)}\b", baixo)
            for variante in _expandir_termo(termo)
        )
    )

    return grupos_no_trecho >= 2


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

    for eh_fallback_or, tsquery_texto in (
        [(False, tsquery_and), (True, tsquery_or)]
        if tsquery_and != tsquery_or
        else [(False, tsquery_and)]
    ):
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
            candidatos = [
                {"id": r[0], "titulo": r[1], "trecho": r[2]}
                for r in rows
                if r and len(r) >= 3 and r[2]
            ]

            # No fallback OU (mais permissivo — casa se QUALQUER termo
            # bater), exige que pelo menos 2 termos distintos apareçam de
            # verdade no trecho, não só o mais genérico dos dois. A busca
            # com E já é seletiva o bastante para não precisar disso.
            if eh_fallback_or:
                candidatos = [
                    c for c in candidatos
                    if _chunk_bate_multiplos_termos(c["trecho"], termos)
                ]

            if candidatos:
                return candidatos

    return []


# Distância de cosseno (pgvector "<=>": 0 = idêntico, mais alto = mais
# distante) acima da qual um chunk é tratado como "não relevante" em vez
# de contexto para o LLM. Calibrado com perguntas reais do histórico da
# Minerva (embedding paraphrase-multilingual-mpnet-base-v2, query_embed):
# perguntas institucionais genuínas ficaram todas em 0.28-0.43
# ("Como funciona o estágio supervisionado?", "Quais as regras de
# trancamento de matrícula?"...); perguntas fora de escopo ficaram todas
# acima de 0.55 ("Quem foi Dom Pedro I do Brasil?", "Qual o time de
# futebol mais forte do Pará?"...). Sem esse corte, a busca semântica
# (ORDER BY ... LIMIT N, sem WHERE) sempre devolve os N chunks mais
# próximos não importa quão distantes estejam de verdade — perguntas sem
# nenhuma relação com a FCT/UFPA acabavam gerando contexto (mesmo que
# ruim) e sendo mandadas ao LLM local, queimando os 2-5min de geração à
# toa numa pergunta que devia cair direto no fallback "não localizei".
SEMANTIC_DISTANCE_MAX = 0.50


def _buscar_semantico(conn, pergunta, limite=10):
    modelo = _get_embedding_model()

    if modelo is None:
        return []

    try:
        vetor = list(modelo.query_embed([pergunta]))[0]
        vetor_literal = "[" + ",".join(f"{v:.6f}" for v in vetor.tolist()) + "]"
    except Exception:
        return []

    sql = """
        SELECT
            id,
            nome_arquivo AS titulo,
            LEFT(conteudo, 2500) AS trecho,
            embedding <=> %s::vector AS distancia
        FROM documentos_ufpa
        WHERE embedding IS NOT NULL
        ORDER BY distancia
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
        if r and len(r) >= 3 and r[2] and r[3] <= SEMANTIC_DISTANCE_MAX
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
    """Pipeline do RAG genérico — última camada do roteador (ver README).

    Passo a passo:

    1. RECUPERAÇÃO — buscar_em_documentos_postgres() roda duas buscas em
       paralelo conceitual sobre a tabela documentos_ufpa:
       a. léxica: full-text search do Postgres (stemmer 'portuguese'),
          com expansão de sinônimos institucionais e estratégia E-depois-OU
          (_buscar_lexico);
       b. semântica: embedding da pergunta via fastembed comparado por
          distância de cosseno com o embedding de cada chunk no pgvector
          (_buscar_semantico).
       Os dois rankings são combinados por Reciprocal Rank Fusion
       (_fusao_rrf), que dispensa calibrar pesos entre escalas de score
       incomparáveis. Saem os 6 melhores chunks.

    2. MONTAGEM DO PROMPT — os chunks viram um bloco "Fonte/Trecho" e são
       embutidos num prompt com as regras institucionais (não inventar,
       não misturar trechos de assuntos diferentes, escopo FCT/UFPA).

    3. GERAÇÃO — llm_func (prompts.consultar_modelo_local) envia o prompt
       ao llama.cpp local (Qwen2.5-7B). Lá dentro ainda existe o prompt de
       sistema institucional e a barreira pós-geração de prompts.py.

    4. SANITIZAÇÃO — sanitizar_resposta() bloqueia qualquer resposta que
       associe a Minerva a instituições homônimas externas (UFPB/UFPE/UPE,
       FCT de Lisboa etc.), mesmo que o modelo tenha ignorado o prompt.

    5. FALLBACK — sem LLM disponível (ou erro na geração), cai para
       resposta_extrativa(): devolve os próprios trechos recuperados,
       citando a fonte, sem gerar texto novo. Sem fontes, admite não saber
       (fallback_sem_base) em vez de inventar.
    """
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
