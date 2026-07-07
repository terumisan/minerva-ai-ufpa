from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ======================================================================
# FONTES OFICIAIS
# ======================================================================

FCT_HOME = "https://fct.ufpa.br/"

FCT_DOCUMENTACAO = (
    "https://fct.ufpa.br/index.php/documentacao"
)

FCT_ESTAGIO = (
    "https://fct.ufpa.br/index.php/estagio"
)

FCT_SOBRE = (
    "https://fct.ufpa.br/index.php/sobre-a-faculdade"
)

FCT_CORPO_DOCENTE = (
    "https://fct.ufpa.br/index.php/corpo-docente"
)

FCT_CONTATO = (
    "https://fct.ufpa.br/index.php/contato"
)

# Regimento específico da Faculdade.
FCT_REGIMENTO = (
    "https://www.fct.ufpa.br/images/stories/"
    "Regimento_FCT.pdf"
)

# Resolução específica de TCC da FCT.
FCT_TCC_RESOLUCAO = (
    "https://fct.ufpa.br/images/stories/"
    "Engcomp_Resolucao_TCC_2012.pdf"
)

PROEG_REGULAMENTO = (
    "https://proeg.ufpa.br/index.php/"
    "regulamento-da-graduacao"
)

PROEG_LEGISLACAO = (
    "https://proeg.ufpa.br/legislacao1"
)

PROEG_CALENDARIO = (
    "https://proeg.ufpa.br/"
    "calendario-academico/62-academico/"
    "calendario-academico"
)

UFPA_LEGISLACAO = (
    "https://portal.ufpa.br/index.php/"
    "sig-ufpa/2-uncategorised/77-legislacao"
)

UFPA_REGIMENTO_GERAL = (
    "https://portal.ufpa.br/images/docs/"
    "regimento_geral.pdf"
)

PROAES_CARDAPIO = (
    "https://proaes.ufpa.br/cardapio"
)


# ======================================================================
# NORMALIZAÇÃO
# ======================================================================

def _norm(text: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        text or "",
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s\-_/]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _has_any(
    text: str,
    markers: tuple[str, ...],
) -> bool:
    return any(
        marker in text
        for marker in markers
    )


# ======================================================================
# CLASSIFICAÇÃO
#
# Ordem proposital:
# documentos específicos vêm antes das respostas genéricas.
# ======================================================================

def classify_priority_question(
    question: str,
) -> Optional[str]:

    if not isinstance(question, str):
        return None

    q = _norm(question)

    if not q:
        return None


    # ------------------------------------------------------------------
    # RU / CARDÁPIO
    # Não interceptar: preserva rota PROAES existente.
    # ------------------------------------------------------------------

    q_tokens = set(
        re.findall(
            r"[a-z0-9]{2,}",
            q,
        )
    )

    if (
        "ru" in q_tokens
        or "cardapio" in q_tokens
        or "bandejao" in q_tokens
        or "restaurante universitario" in q
    ):
        return None


    # ------------------------------------------------------------------
    # REGIMENTO ESPECÍFICO DA FCT
    # ------------------------------------------------------------------

    if (
        "regimento" in q
        and _has_any(
            q,
            (
                "fct",
                "faculdade",
                "faculdade de engenharia",
            ),
        )
        and "geral da ufpa" not in q
    ):
        return "fct_regiment"


    # ------------------------------------------------------------------
    # REGIMENTO GERAL UFPA
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "regimento geral da ufpa",
            "regimento geral ufpa",
            "regimento geral da universidade",
            "me mostre o regimento geral",
            "mostrar o regimento geral",
            "quero o regimento geral",
        ),
    ):
        return "ufpa_general_regiment"


    # ------------------------------------------------------------------
    # TCC
    # ------------------------------------------------------------------

    if (
        "tcc" in q
        or "trabalho de conclusao" in q
        or "trabalho de curso" in q
    ):
        return "tcc"


    # ------------------------------------------------------------------
    # REGULAMENTO DA GRADUAÇÃO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "regulamento de graduacao",
            "regulamento da graduacao",
            "regulamento do ensino de graduacao",
            "regras da graduacao",
            "normas da graduacao",
            "regulamento graduacao",
        ),
    ):
        return "graduation_regulation"


    # ------------------------------------------------------------------
    # NORMAS PARA DISCENTES
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "normas gerais se aplicam aos discentes",
            "normas para os discentes",
            "regras para os discentes",
            "direitos dos alunos",
            "deveres dos alunos",
            "normas dos alunos",
        ),
    ):
        return "student_rules"


    # ------------------------------------------------------------------
    # REGRAS INSTITUCIONAIS DA FACULDADE
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "regras institucionais da faculdade",
            "normas institucionais da faculdade",
            "normas da fct",
            "regras da fct",
            "normas fct ufpa",
            "normas fct",
        ),
    ):
        return "fct_rules"


    # ------------------------------------------------------------------
    # ACESSO RÁPIDO: CALENDÁRIO
    # ------------------------------------------------------------------

    if (
        q == "calendario"
        or _has_any(
            q,
            (
                "calendario academico",
                "quando comecam as aulas",
                "quando começam as aulas",
            ),
        )
    ):
        return "calendar"


    # ------------------------------------------------------------------
    # ACESSO RÁPIDO: ESTÁGIO
    # ------------------------------------------------------------------

    if (
        q == "estagio"
        or "regras de estagio" in q
        or "como funciona o estagio" in q
        or "informacoes de estagio" in q
    ):
        return "internship"


    # ------------------------------------------------------------------
    # ACESSO RÁPIDO: GRADUAÇÃO
    # ------------------------------------------------------------------

    if q in {
        "graduacao",
        "graduacao ufpa",
    }:
        return "graduation"


    # ------------------------------------------------------------------
    # DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "documentacao da fct",
            "documentos da fct",
            "onde encontro formularios",
            "onde encontro documentos",
        ),
    ):
        return "documentation"


    # ------------------------------------------------------------------
    # CURSOS
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "quais cursos a fct oferece",
            "quais cursos da fct",
            "cursos a fct oferece",
            "cursos da fct",
        ),
    ):
        return "courses"


    # ------------------------------------------------------------------
    # IDENTIDADE FCT
    # Somente perguntas explicitamente sobre a sigla.
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "o que significa fct",
            "fct significa o que",
            "qual o significado de fct",
            "o que e a fct",
        ),
    ):
        return "fct_identity"


    # ------------------------------------------------------------------
    # IDENTIDADE UFPA
    # Somente pergunta explícita.
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "o que significa ufpa",
            "ufpa significa o que",
            "qual o significado de ufpa",
        ),
    ):
        return "ufpa_identity"


    return None


# ======================================================================
# RESPOSTAS PRIORITÁRIAS
# ======================================================================

def priority_answer(
    question: str,
) -> Optional[str]:

    route = classify_priority_question(
        question
    )

    if route is None:
        return None


    # ------------------------------------------------------------------
    # REGIMENTO FCT
    # ------------------------------------------------------------------

    if route == "fct_regiment":
        return (
            "O Regimento da FCT disciplina a organização da Faculdade, "
            "abrangendo sua denominação, objetivos e atuação, estrutura "
            "organizacional, Conselho da Faculdade, Direção, Secretaria "
            "Executiva, laboratórios de ensino e pesquisa, organização "
            "didática e disposições finais. "
            "Para consultar o conteúdo integral, use o documento oficial. "
            f"Fonte oficial: {FCT_REGIMENTO}"
        )


    # ------------------------------------------------------------------
    # REGIMENTO GERAL UFPA
    # ------------------------------------------------------------------

    if route == "ufpa_general_regiment":
        return (
            "O Regimento Geral da UFPA disciplina a organização e o "
            "funcionamento institucional da Universidade e deve ser lido "
            "em conjunto com o Estatuto e as normas específicas das "
            "unidades acadêmicas. A UFPA disponibiliza o documento integral "
            "em seu portal oficial de legislação. "
            f"Regimento Geral: {UFPA_REGIMENTO_GERAL} "
            f"| Legislação institucional: {UFPA_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # TCC
    # ------------------------------------------------------------------

    if route == "tcc":
        return (
            "Na FCT, o TCC possui regulamentação específica. A Resolução "
            "FCT 01/2012 estabelece diretrizes para a elaboração dos "
            "Trabalhos de Conclusão de Curso no âmbito dos cursos de "
            "Engenharia da Computação e Engenharia de Telecomunicações. "
            "Além disso, a seção de Documentação da FCT reúne instruções "
            "sobre matrícula, agendamento de defesa e entrega da "
            "documentação após a defesa. "
            f"Resolução oficial: {FCT_TCC_RESOLUCAO} "
            f"| Documentação FCT: {FCT_DOCUMENTACAO}"
        )


    # ------------------------------------------------------------------
    # REGULAMENTO DA GRADUAÇÃO
    # ------------------------------------------------------------------

    if route == "graduation_regulation":
        return (
            "O Regulamento do Ensino de Graduação da UFPA reúne normas "
            "gerais da vida acadêmica da graduação e se articula com o "
            "Estatuto, o Regimento Geral da Universidade e os regimentos "
            "das unidades acadêmicas. Para uma resposta mais específica, "
            "a pergunta pode indicar o tema desejado, por exemplo: "
            "matrícula, aproveitamento de estudos, avaliação, trancamento "
            "ou integralização curricular. "
            f"Fonte oficial PROEG: {PROEG_REGULAMENTO} "
            f"| Legislação da graduação: {PROEG_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # NORMAS DOS DISCENTES
    # ------------------------------------------------------------------

    if route == "student_rules":
        return (
            "As normas aplicáveis aos discentes da FCT resultam de uma "
            "hierarquia institucional: Regimento Geral da UFPA, Regulamento "
            "do Ensino de Graduação, regimento da própria Faculdade e "
            "resoluções específicas, como as normas de TCC. A regra exata "
            "depende do assunto acadêmico consultado. "
            f"Regulamento da Graduação: {PROEG_REGULAMENTO} "
            f"| Regimento da FCT: {FCT_REGIMENTO} "
            f"| Legislação UFPA: {UFPA_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # NORMAS DA FCT
    # ------------------------------------------------------------------

    if route == "fct_rules":
        return (
            "As regras institucionais da FCT devem ser consultadas primeiro "
            "no Regimento da Faculdade e na seção oficial de Documentação. "
            "Para assuntos específicos também existem resoluções próprias, "
            "como a regulamentação de TCC. "
            f"Regimento FCT: {FCT_REGIMENTO} "
            f"| Documentação FCT: {FCT_DOCUMENTACAO} "
            f"| Resolução de TCC: {FCT_TCC_RESOLUCAO}"
        )


    # ------------------------------------------------------------------
    # CALENDÁRIO
    # ------------------------------------------------------------------

    if route == "calendar":
        return (
            "O calendário acadêmico oficial da UFPA é mantido pela PROEG. "
            "A página reúne o calendário vigente e versões de anos "
            "anteriores. Para perguntas sobre uma data específica, informe "
            "o evento desejado, como matrícula, início das aulas ou término "
            "do período letivo. "
            f"Fonte oficial: {PROEG_CALENDARIO}"
        )


    # ------------------------------------------------------------------
    # ESTÁGIO
    # ------------------------------------------------------------------

    if route == "internship":
        return (
            "A FCT possui uma página específica para estágio, com "
            "informações e procedimentos relacionados a estágio obrigatório "
            "e não obrigatório. Para uma regra detalhada, informe o tema, "
            "como documentação, integralização, assinatura ou carga horária. "
            f"Fonte oficial: {FCT_ESTAGIO}"
        )


    # ------------------------------------------------------------------
    # GRADUAÇÃO
    # ------------------------------------------------------------------

    if route == "graduation":
        return (
            "Para assuntos de graduação, a Minerva deve priorizar as regras "
            "específicas da FCT e, em seguida, o Regulamento do Ensino de "
            "Graduação da UFPA e a legislação mantida pela PROEG. "
            f"Regulamento oficial: {PROEG_REGULAMENTO} "
            f"| Legislação PROEG: {PROEG_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if route == "documentation":
        return (
            "A FCT mantém uma seção oficial de Documentação com materiais "
            "acadêmicos e instruções para procedimentos da Faculdade, "
            "incluindo orientações relacionadas a TCC. "
            f"Fonte oficial: {FCT_DOCUMENTACAO}"
        )


    # ------------------------------------------------------------------
    # CURSOS
    # ------------------------------------------------------------------

    if route == "courses":
        return (
            "A FCT/UFPA oferece os cursos de Engenharia da Computação e "
            "Engenharia de Telecomunicações. "
            f"Fonte oficial: {FCT_SOBRE}"
        )


    # ------------------------------------------------------------------
    # IDENTIDADE FCT
    # ------------------------------------------------------------------

    if route == "fct_identity":
        return (
            "FCT é a Faculdade de Engenharia da Computação e "
            "Telecomunicações da Universidade Federal do Pará. "
            f"Fonte oficial: {FCT_SOBRE}"
        )


    # ------------------------------------------------------------------
    # IDENTIDADE UFPA
    # ------------------------------------------------------------------

    if route == "ufpa_identity":
        return (
            "UFPA significa Universidade Federal do Pará. "
            "Esta resposta é usada somente quando a pergunta solicita "
            "explicitamente o significado da sigla."
        )


    return None


def debug_priority(
    question: str,
) -> dict:
    return {
        "question": question,
        "route": classify_priority_question(
            question
        ),
        "answer": priority_answer(
            question
        ),
    }


__all__ = [
    "classify_priority_question",
    "priority_answer",
    "debug_priority",
]
