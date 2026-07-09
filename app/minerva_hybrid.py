import re

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


def buscar_em_documentos_postgres(conn, pergunta, limite=5):
    if conn is None:
        return []

    # Schema real (ver app/scripts/ingestao.py): apenas id, nome_arquivo, conteudo.
    # Consultas antigas aqui referenciavam colunas inexistentes (titulo, texto,
    # texto_extraido), o que derrubava a query com "column does not exist" e
    # fazia esta função sempre devolver [] silenciosamente.
    #
    # Antes havia também uma cláusula "conteudo ILIKE %pergunta%" (a pergunta
    # inteira, sem tokenizar) em OR com o tsquery — na prática ela nunca
    # contribuía com nenhum resultado extra (exige a frase inteira, literal,
    # dentro do chunk) e ainda forçava um scan textual extra na tabela.
    termos = _termos_relevantes(pergunta)

    if not termos:
        return []

    sql = """
        SELECT
            nome_arquivo AS titulo,
            LEFT(conteudo, 2500) AS trecho
        FROM documentos_ufpa
        WHERE
            to_tsvector('portuguese', conteudo) @@ to_tsquery('portuguese', %s)
        ORDER BY
            ts_rank_cd(to_tsvector('portuguese', conteudo), to_tsquery('portuguese', %s)) DESC
        LIMIT %s
    """

    # Bug real: OR puro entre todos os termos ("trancar | curso") deixava uma
    # palavra genérica e frequente ("curso", presente em quase todo chunk
    # institucional) dominar o ranking sobre o termo raro e realmente
    # relevante ("trancar"/"trancamento") — "Como trancar o curso?" retornava
    # só trechos sobre "cursos de especialização" e nunca o trecho real sobre
    # trancamento, mesmo ele existindo na base (Regulamento_Graduacao.pdf).
    # Estratégia: tentar E lógico (todos os termos, mais preciso) primeiro;
    # só cair para OU (mais abrangente) se a busca com E não achar nada.
    #
    # ":*" (prefixo) em cada termo: o stemmer 'portuguese' reduz "trancar" a
    # 'tranc' e "trancamento" a 'trancament' — lexemas DIFERENTES apesar de
    # serem a mesma família de palavra. Sem prefixo, "trancar & curso" nunca
    # batia com o trecho real (que só tem "Trancamento", não "trancar"/
    # "tranca"). "tranc:*" casa com qualquer lexema começando por "tranc",
    # cobrindo variações morfológicas (trancar/tranca/trancamento/...).
    termos_prefixo = [f"{termo}:*" for termo in termos]
    tsquery_and = " & ".join(termos_prefixo)
    tsquery_or = " | ".join(termos_prefixo)

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
                {
                    "titulo": r[0],
                    "trecho": r[1],
                    "fonte": "Base documental local",
                }
                for r in rows
                if r and len(r) >= 2 and r[1]
            ]

    return []

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
