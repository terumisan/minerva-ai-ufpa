import re

SIGLAS_FIXAS = {
    "FCT": "Faculdade de Computação e Telecomunicações, no contexto da Universidade Federal do Pará (UFPA).",
    "UFPA": "Universidade Federal do Pará.",
    "PROEG": "Pró-Reitoria de Ensino de Graduação da Universidade Federal do Pará.",
    "CIAC": "Centro de Registro e Indicadores Acadêmicos da Universidade Federal do Pará.",
    "SIGAA": "Sistema Integrado de Gestão de Atividades Acadêmicas.",
}

TERMOS_BLOQUEADOS = [
    "universidade federal de pernambuco",
    "universidade federal da paraíba",
    "universidade federal da paraiba",
    "universidade de pernambuco",
    "faculdade de ciências técnicas",
    "faculdade de ciencias tecnicas",
    "ufpb",
    "ufpe",
    "upe",
]

def fallback_sem_base():
    return (
        "Não localizei informação institucional suficiente na base disponível "
        "da FCT/UFPA para responder com segurança."
    )

def resposta_sigla(pergunta):
    texto = pergunta.upper()

    for sigla, significado in SIGLAS_FIXAS.items():
        if re.search(rf"\b{re.escape(sigla)}\b", texto):
            return f"**{sigla}** significa **{significado}**"

    return None

def sanitizar_resposta(resposta):
    if not resposta:
        return fallback_sem_base()

    baixo = resposta.lower()

    if any(t in baixo for t in TERMOS_BLOQUEADOS):
        return (
            "Não localizei informação institucional segura na base da FCT/UFPA "
            "para responder sem risco de erro.\n\n"
            "**Referência correta:**\n"
            "- **FCT:** Faculdade de Computação e Telecomunicações\n"
            "- **UFPA:** Universidade Federal do Pará"
        )

    return resposta

def buscar_em_documentos_postgres(conn, pergunta, limite=5):
    if conn is None:
        return []

    consultas = [
        """
        SELECT
            COALESCE(titulo, nome_arquivo, 'Documento institucional') AS titulo,
            LEFT(COALESCE(conteudo, texto, ''), 2500) AS trecho
        FROM documentos_ufpa
        WHERE
            COALESCE(conteudo, texto, '') ILIKE '%' || %s || '%'
            OR to_tsvector('portuguese', COALESCE(conteudo, texto, ''))
               @@ plainto_tsquery('portuguese', %s)
        LIMIT %s
        """,
        """
        SELECT
            COALESCE(nome_arquivo, titulo, 'Documento institucional') AS titulo,
            LEFT(COALESCE(texto_extraido, conteudo, texto, ''), 2500) AS trecho
        FROM documentos_ufpa
        WHERE
            COALESCE(texto_extraido, conteudo, texto, '') ILIKE '%' || %s || '%'
        LIMIT %s
        """
    ]

    for sql in consultas:
        try:
            cur = conn.cursor()
            if sql.count("%s") == 3:
                cur.execute(sql, (pergunta, pergunta, limite))
            else:
                cur.execute(sql, (pergunta, limite))

            rows = cur.fetchall()
            cur.close()

            achados = []
            for r in rows:
                if r and len(r) >= 2 and r[1]:
                    achados.append({
                        "titulo": r[0],
                        "trecho": r[1],
                        "fonte": "Base documental local"
                    })

            if achados:
                return achados

        except Exception:
            try:
                cur.close()
            except Exception:
                pass

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
    direta = resposta_sigla(pergunta)
    if direta:
        return direta

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
