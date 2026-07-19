from __future__ import annotations

import re

import requests
import streamlit as st

# MINERVA_PROMPTS_CONFIG_IMPORT_BEGIN
try:
    from .config import LLM_API_URL, logger
except (ImportError, ValueError):
    from config import LLM_API_URL, logger
# MINERVA_PROMPTS_CONFIG_IMPORT_END


# ======================================================================
# MINERVA AI
# Escopo institucional rígido (FCT/UFPA): prompt de sistema, barreiras
# antes/depois da geração e chamada ao modelo local (llama.cpp).
# ======================================================================

NOME_UFPA = "Universidade Federal do Pará"
SIGLA_UFPA = "UFPA"
NOME_FCT = "Faculdade de Computação e Telecomunicações"
SIGLA_FCT = "FCT"

PROMPT_INSTITUCIONAL_UFPA = """
Você é a Minerva, assistente virtual acadêmica da
Faculdade de Computação e Telecomunicações (FCT)
da Universidade Federal do Pará (UFPA).

ESCOPO INSTITUCIONAL OBRIGATÓRIO:

1. UFPA significa exclusivamente Universidade Federal do Pará.
2. FCT significa exclusivamente Faculdade de Computação e Telecomunicações.
3. A FCT tratada nesta aplicação pertence ao contexto da UFPA.
4. Toda pergunta acadêmica ambígua deve ser interpretada primeiro no contexto
   da FCT/UFPA.
5. Nunca associe a FCT desta aplicação à UFPB, UFPE, UPE ou a qualquer outra
   universidade.
6. Nunca diga que FCT significa Faculdade de Ciências Técnicas.
7. Nunca diga que a UFPA é Universidade Federal de Pernambuco,
   Universidade Federal da Paraíba ou qualquer outra instituição.
8. Não transfira informações, currículos, duração de cursos, disciplinas,
   regulamentos, calendários, campi ou procedimentos de outras universidades
   para a UFPA.
9. Não invente normas, artigos, resoluções, prazos, datas, requisitos,
   estruturas curriculares, duração de cursos, número de semestres ou
   procedimentos acadêmicos.
10. Quando não houver base institucional suficiente, diga explicitamente:
    "Não localizei informação institucional suficiente na base disponível
    da FCT/UFPA para responder com segurança."
11. Se a pergunta mencionar explicitamente outra universidade, informe
    educadamente que o escopo da Minerva está restrito à FCT/UFPA.
12. Para perguntas como "para que serve o curso", "como funciona o curso",
    "quantos semestres possui" ou "quais disciplinas existem", não invente
    detalhes. Responda apenas com informações institucionais seguras.
13. Antes de concluir cada resposta, confira mentalmente:
    - FCT = Faculdade de Computação e Telecomunicações;
    - UFPA = Universidade Federal do Pará;
    - nenhuma instituição externa foi usada como fonte implícita.

ESTILO:
- Responda em português do Brasil.
- Seja claro, direto e acadêmico.
- Não crie fatos para preencher lacunas.
- Não mencione outras universidades como se fossem a UFPA.
"""


def pergunta_menciona_instituicao_externa(pergunta: str) -> bool:
    """
    Detecta quando o usuário explicitamente direciona a pergunta
    para outra instituição.

    Perguntas sem instituição explícita continuam sendo interpretadas
    no contexto padrão FCT/UFPA.
    """
    texto = pergunta.casefold()

    # Detecta siglas UFxx diferentes de UFPA.
    siglas = re.findall(r"\buf[a-z]{1,4}\b", texto)

    if any(sigla != "ufpa" for sigla in siglas):
        return True

    # "FCT" sozinha não basta pra bloquear (é a sigla da própria FCT/UFPA),
    # mas "FCT" associada a Portugal/Lisboa é o mesmo caso de confusão com
    # a Faculdade de Ciências e Tecnologia da Universidade Nova de Lisboa
    # (ver TERMOS_BLOQUEADOS_FRASES em minerva_hybrid.py). Pergunta como
    # "O que é a FCT de Portugal?" não repete o nome completo da instituição
    # portuguesa, então a checagem por frase abaixo sozinha não pega.
    if "fct" in texto and (
        any(termo in texto for termo in ("portugal", "português", "portugues", "lisboa"))
        # "UNL" (Universidade Nova de Lisboa) é curta demais pra substring
        # simples — "\b" evita casar dentro de outra palavra.
        or re.search(r"\bunl\b", texto)
    ):
        return True

    instituicoes_externas = (
        "universidade federal de pernambuco",
        "universidade federal da paraíba",
        "universidade federal da paraiba",
        "universidade de pernambuco",
        "universidade federal do ceará",
        "universidade federal do ceara",
        "universidade federal do rio grande do norte",
        "universidade federal do rio de janeiro",
        "universidade de são paulo",
        "universidade de sao paulo",
        # A FCT/UFPA (Faculdade de Computação e Telecomunicações) tem o
        # mesmo nome/sigla da Faculdade de Ciências e Tecnologia da
        # Universidade Nova de Lisboa, também conhecida como "FCT" em
        # Portugal — ver mesmo bloqueio em minerva_hybrid.py e em
        # validar_resposta_institucional() logo abaixo.
        "faculdade de ciências e tecnologia",
        "faculdade de ciencias e tecnologia",
        "universidade nova de lisboa",
    )

    return any(nome in texto for nome in instituicoes_externas)


def validar_resposta_institucional(resposta: str) -> str:
    """
    Barreira pós-geração.

    Mesmo que o modelo ignore parcialmente o prompt, uma resposta
    contendo associação institucional incompatível não chega ao usuário.
    """
    if not resposta:
        return (
            "Não localizei informação institucional suficiente na base disponível "
            "da FCT/UFPA para responder com segurança."
        )

    texto = resposta.casefold()

    associacoes_invalidas = (
        "universidade federal de pernambuco",
        "universidade federal da paraíba",
        "universidade federal da paraiba",
        "universidade de pernambuco",
        "faculdade de ciências técnicas",
        "faculdade de ciencias tecnicas",
        # Mesmo caso de confusão FCT/Portugal (Universidade Nova de Lisboa)
        # documentado em minerva_hybrid.py e em
        # pergunta_menciona_instituicao_externa() acima.
        "faculdade de ciências e tecnologia",
        "faculdade de ciencias e tecnologia",
        "universidade nova de lisboa",
    )

    # Mesma lógica de pergunta_menciona_instituicao_externa(): "FCT" sozinha
    # é a sigla da própria FCT/UFPA, mas "FCT" associada a Portugal/Lisboa
    # indica que o modelo confundiu com a FCT da Universidade Nova de
    # Lisboa sem necessariamente repetir o nome completo da instituição.
    fct_portugal = "fct" in texto and (
        any(termo in texto for termo in ("portugal", "português", "portugues", "lisboa"))
        or re.search(r"\bunl\b", texto)
    )

    if fct_portugal or any(termo in texto for termo in associacoes_invalidas):
        logger.warning(
            "Resposta bloqueada por associação institucional incompatível: %s",
            resposta,
        )
        return (
            "Não localizei informação institucional suficiente na base disponível "
            "da FCT/UFPA para responder com segurança.\n\n"
            "**Referência institucional correta:**\n"
            "- **FCT:** Faculdade de Computação e Telecomunicações\n"
            "- **UFPA:** Universidade Federal do Pará"
        )

    # Bloqueia siglas UFxx externas produzidas pelo modelo.
    siglas = re.findall(r"\buf[a-z]{1,4}\b", texto)

    if any(sigla != "ufpa" for sigla in siglas):
        logger.warning(
            "Resposta bloqueada por sigla institucional externa: %s",
            resposta,
        )
        return (
            "A Minerva está configurada para responder exclusivamente no contexto "
            "da Faculdade de Computação e Telecomunicações da Universidade Federal "
            "do Pará — FCT/UFPA."
        )

    return resposta


@st.cache_resource(show_spinner=False)
def get_http_session() -> requests.Session:
    """Cria sessão HTTP reutilizável para chamadas ao modelo local."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


http_session = get_http_session()


def consultar_modelo_local(pergunta: str) -> str:
    """
    Consulta a API local compatível com /v1/chat/completions.

    A resposta é submetida a duas barreiras:
    1. prompt institucional rígido;
    2. validação pós-geração.

    Nota: este método recebe o PROMPT JÁ MONTADO (pergunta + contexto do
    RAG + instruções), não a pergunta crua do usuário — por isso a checagem
    de instituição externa não é feita aqui (ver processar_pergunta). O
    próprio texto do PROMPT_INSTITUCIONAL_UFPA cita "UFPB, UFPE, UPE" como
    exemplos do que não confundir, e checar essas palavras aqui gerava
    falso positivo em toda pergunta que chegasse a este ponto.

    Bug real: este método envolvia "pergunta" (que já é o prompt inteiro
    montado por responder_minerva, com regras + contexto RAG + a pergunta
    real) num segundo wrapper ("Considere obrigatoriamente... Pergunta do
    usuário: <prompt inteiro>"). O resultado era um "Pergunta do usuário"
    contendo, ele mesmo, outro bloco "Pergunta:" lá dentro — confuso para
    um modelo pequeno (3B), que podia perder o foco na pergunta real em
    meio a instruções duplicadas. Envia-se "pergunta" direto como conteúdo
    do usuário: ela já está completa.
    """
    payload = {
        "messages": [
            {
                "role": "system",
                "content": PROMPT_INSTITUCIONAL_UFPA,
            },
            {
                "role": "user",
                "content": pergunta,
            },
        ],
        "temperature": 0.0,
        "max_tokens": 450,
        # O Gemma 4 "pensa" antes de responder por padrão (gasta ~400
        # tokens em raciocínio interno numa pergunta de 4 palavras, estourando
        # o max_tokens antes de gerar a resposta de verdade). Modelos sem
        # esse recurso (Qwen, Llama) simplesmente ignoram o campo.
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        response = http_session.post(
            LLM_API_URL,
            json=payload,
            # 12s originais eram menores que o tempo real de resposta do
            # modelo local em CPU. Medido no i5-1245U com o Qwen2.5-7B
            # Q4_K_M: ~14 tok/s lendo o prompt e ~2,5 tok/s gerando —
            # uma resposta RAG completa leva de 2 a 5 minutos. 420s cobre
            # o pior caso com folga; abaixo disso o request estourava
            # antes de o modelo terminar.
            timeout=420,
        )

        if response.status_code != 200:
            logger.warning(
                "Modelo retornou status %s: %s",
                response.status_code,
                response.text,
            )
            return (
                "Não localizei informação institucional suficiente na base "
                "disponível da FCT/UFPA para responder com segurança."
            )

        data = response.json()

        resposta = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        return validar_resposta_institucional(resposta)

    except Exception as exc:
        logger.exception(
            "Erro ao consultar modelo local da Minerva: %s",
            exc,
        )
        return (
            "No momento, não foi possível consultar a base assistida da FCT/UFPA. "
            "Tente novamente mais tarde."
        )
