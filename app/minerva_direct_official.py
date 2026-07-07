from __future__ import annotations

import re
import time
import unicodedata

from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# ======================================================================
# MINERVA AI
# Roteamento institucional direto.
#
# Política:
# 1. FCT primeiro para assuntos locais.
# 2. UFPA oficial para normas gerais.
# 3. PROEG para graduação.
# 4. Não deixar "UFPA" isoladamente capturar perguntas documentais.
# 5. RU/PROAES permanece fora desta rota.
#
# Sem pip.
# Sem requests.
# Sem BeautifulSoup.
# ======================================================================


# ----------------------------------------------------------------------
# FCT
# ----------------------------------------------------------------------

FCT_BASE = "https://fct.ufpa.br"

URL_FCT_ABOUT = (
    "https://fct.ufpa.br/index.php/sobre-a-faculdade"
)

URL_FCT_CONTACT = (
    "https://fct.ufpa.br/index.php/contato"
)

URL_FCT_FACULTY = (
    "https://fct.ufpa.br/index.php/corpo-docente"
)

URL_FCT_DOCS = (
    "https://fct.ufpa.br/index.php/documentacao"
)

URL_FCT_INTERNSHIP = (
    "https://fct.ufpa.br/index.php/estagio"
)

URL_FCT_HISTORY = (
    "https://fct.ufpa.br/index.php/historico"
)


# ----------------------------------------------------------------------
# UFPA / PROEG / SEGE
# ----------------------------------------------------------------------

URL_GRAD_REGULATION_PAGE = (
    "https://proeg.ufpa.br/index.php/regulamento-da-graduacao"
)

URL_GRAD_REGULATION_PDF = (
    "https://sege.ufpa.br/boletim_interno/downloads/"
    "resolucoes/consepe/2013/"
    "4399%20Reg%20Gradua%C3%A7%C3%A3o.pdf"
)

URL_PROEG_LEGISLATION = (
    "https://proeg.ufpa.br/legislacao1"
)

URL_UFPA_LEGISLATION = (
    "https://portal.ufpa.br/index.php/"
    "sig-ufpa/2-uncategorised/77-legislacao"
)

URL_GENERAL_REGIMENT_PDF = (
    "https://portal.ufpa.br/images/docs/regimento_geral.pdf"
)


TIMEOUT = 10
CACHE_TTL = 15 * 60


_HTML_CACHE: Dict[
    str,
    Tuple[float, str],
] = {}


# ======================================================================
# NORMALIZAÇÃO
# ======================================================================


def _normalize(text: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        text or "",
    )

    text = "".join(
        ch
        for ch in text
        if not unicodedata.combining(ch)
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


def _tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"[a-z0-9]{2,}",
            _normalize(text),
        )
    )


# ======================================================================
# DOMÍNIOS OFICIAIS
# ======================================================================


def _is_official_ufpa_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        host = (
            parsed.hostname
            or ""
        ).lower().strip(".")

        scheme = (
            parsed.scheme
            or ""
        ).lower()

        return (
            scheme in {"http", "https"}
            and (
                host == "ufpa.br"
                or host.endswith(".ufpa.br")
            )
        )

    except Exception:
        return False


# ======================================================================
# CLASSIFICAÇÃO
#
# ORDEM É DELIBERADA:
# normas/documentos antes de identidade UFPA/FCT.
# ======================================================================


def detect_direct_intent(
    question: str,
) -> Optional[str]:

    if not isinstance(question, str):
        return None

    q = _normalize(question)

    if not q:
        return None

    q_tokens = _tokens(q)


    # ------------------------------------------------------------------
    # 0. RU / PROAES
    # Não interceptar.
    # ------------------------------------------------------------------

    if (
        "ru" in q_tokens
        or "cardapio" in q_tokens
        or "bandejao" in q_tokens
        or "proaes" in q_tokens
        or "restaurante universitario" in q
    ):
        return None


    # ------------------------------------------------------------------
    # 1. REGULAMENTO DE GRADUAÇÃO
    # Deve vir antes de "UFPA identity".
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "regulamento de graduacao",
            "regulamento da graduacao",
            "regulamento do ensino de graduacao",
            "regulamento ensino de graduacao",
            "regras da graduacao",
            "normas da graduacao",
            "normas de graduacao",
            "o que diz o regulamento de graduacao",
            "me mostre o regulamento de graduacao",
        )
    ):
        return "graduation_regulation"


    # ------------------------------------------------------------------
    # 2. REGIMENTO GERAL DA UFPA
    # Deve vir antes de identidade UFPA.
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "regimento geral da ufpa",
            "regimento geral ufpa",
            "regimento da ufpa",
            "me mostre o regimento geral",
            "mostrar o regimento geral",
            "quero o regimento geral",
            "qual e o regimento geral",
            "o que diz o regimento geral",
        )
    ):
        return "general_regiment"


    # ------------------------------------------------------------------
    # 3. ESTATUTO DA UFPA
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "estatuto da ufpa",
            "estatuto geral da ufpa",
            "me mostre o estatuto",
            "o que diz o estatuto da ufpa",
        )
    ):
        return "ufpa_statute"


    # ------------------------------------------------------------------
    # 4. TCC / TRABALHO DE CURSO
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "regulamento do tcc",
            "regulamento de tcc",
            "regras do tcc",
            "normas do tcc",
            "como funciona o tcc",
            "trabalho de conclusao",
            "trabalho de curso",
            "modelo de tcc",
            "template de tcc",
            "overleaf",
        )
    ):
        return "tcc"


    # ------------------------------------------------------------------
    # 5. DIREÇÃO
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "diretor",
            "diretora",
            "vice diretor",
            "vice-diretor",
            "vice diretora",
            "vice-diretora",
            "direcao",
            "quem dirige",
        )
    ):
        return "leadership"


    # ------------------------------------------------------------------
    # 6. PROFESSORES
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "professor",
            "professores",
            "docente",
            "docentes",
            "corpo docente",
            "quem da aula",
        )
    ):
        return "faculty"


    # ------------------------------------------------------------------
    # 7. CURSOS
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "quais cursos",
            "qual curso",
            "cursos da fct",
            "cursos a fct",
            "cursos oferece",
            "curso oferece",
            "engenharia da computacao",
            "engenharia de telecomunicacoes",
        )
    ):
        return "courses"


    # ------------------------------------------------------------------
    # 8. CONTATO
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "telefone",
            "contato",
            "email",
            "e mail",
            "secretaria",
            "endereco",
            "localizacao",
            "onde fica a fct",
        )
    ):
        return "contact"


    # ------------------------------------------------------------------
    # 9. ESTÁGIO
    # ------------------------------------------------------------------

    if "estagio" in q:
        return "internship"


    # ------------------------------------------------------------------
    # 10. MATRÍCULA
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "matricula",
            "matricular",
            "sigaa",
            "ajuste de matricula",
        )
    ):
        return "enrollment"


    # ------------------------------------------------------------------
    # 11. DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "documento",
            "documentacao",
            "formulario",
            "formularios",
            "requerimento",
        )
    ):
        return "documentation"


    # ------------------------------------------------------------------
    # 12. IDENTIDADE FCT
    #
    # Somente expressões explícitas.
    # "FCT" sozinho NÃO basta.
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "o que significa fct",
            "fct significa o que",
            "fct significa",
            "o que e a fct",
            "o que e fct",
            "nome completo da fct",
        )
    ):
        return "fct_identity"


    # ------------------------------------------------------------------
    # 13. IDENTIDADE UFPA
    #
    # Somente pergunta explícita sobre sigla.
    # "regimento da UFPA" jamais chega aqui.
    # ------------------------------------------------------------------

    if any(
        marker in q
        for marker in (
            "o que significa ufpa",
            "ufpa significa o que",
            "qual o significado de ufpa",
            "o que e a ufpa",
        )
    ):
        return "ufpa_identity"


    return None


# ======================================================================
# PARSER HTML
# ======================================================================


class _TextParser(HTMLParser):

    SKIP_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "canvas",
    }

    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.skip_depth = 0
        self.pieces: List[str] = []


    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:

        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1


    def handle_endtag(
        self,
        tag: str,
    ) -> None:

        if (
            tag.lower() in self.SKIP_TAGS
            and self.skip_depth
        ):
            self.skip_depth -= 1


    def handle_data(
        self,
        data: str,
    ) -> None:

        if self.skip_depth:
            return

        text = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if text:
            self.pieces.append(text)


def _fetch(url: str) -> str:

    if not _is_official_ufpa_url(url):
        return ""

    cached = _HTML_CACHE.get(url)

    if cached:
        created, content = cached

        if (
            time.time() - created
            <= CACHE_TTL
        ):
            return content

    request = Request(
        url,
        headers={
            "User-Agent": (
                "MinervaAI-UFPA/6.0 "
                "(assistente institucional)"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
            "Accept-Language": (
                "pt-BR,pt;q=0.9"
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=TIMEOUT,
        ) as response:

            final_url = response.geturl()

            if not _is_official_ufpa_url(
                final_url
            ):
                return ""

            raw = response.read()

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            try:
                content = raw.decode(
                    charset,
                    errors="replace",
                )

            except LookupError:
                content = raw.decode(
                    "utf-8",
                    errors="replace",
                )

            _HTML_CACHE[url] = (
                time.time(),
                content,
            )

            return content

    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
    ):
        return ""


def _page_text(url: str) -> str:

    content = _fetch(url)

    if not content:
        return ""

    parser = _TextParser()

    try:
        parser.feed(content)
        parser.close()

    except Exception:
        pass

    return "\n".join(
        parser.pieces
    )


# ======================================================================
# EXTRAÇÕES
# ======================================================================


def _label_value(
    text: str,
    labels: Sequence[str],
) -> Optional[str]:

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    normalized_labels = {
        _normalize(label)
        for label in labels
    }

    for index, line in enumerate(lines):

        normalized_line = _normalize(
            line
        )

        for label in labels:

            match = re.match(
                rf"^\s*"
                rf"{re.escape(label)}"
                rf"\s*:\s*(.+)$",
                line,
                flags=re.I,
            )

            if match:
                value = match.group(1).strip()

                if value:
                    return value

        if (
            normalized_line.rstrip(":")
            in normalized_labels
            and index + 1 < len(lines)
        ):
            value = lines[
                index + 1
            ].strip()

            if value:
                return value

    return None


def _faculty_list(
    text: str,
) -> List[str]:

    results: List[str] = []
    seen = set()

    pattern = re.compile(
        r"^\s*"
        r"([A-ZÀ-ÖØ-Ý]"
        r"[A-ZÀ-ÖØ-Ý0-9 .'\-]{3,150})"
        r"\s*"
        r"\("
        r"(DOUTOR|DOUTORA|MESTRE|MESTRA)"
        r"\)"
        r"\s*$"
    )

    for line in text.splitlines():

        match = pattern.match(
            line.strip()
        )

        if not match:
            continue

        name = re.sub(
            r"\s+",
            " ",
            match.group(1),
        ).strip().title()

        degree = (
            match.group(2)
            .strip()
            .title()
        )

        key = _normalize(name)

        if key in seen:
            continue

        seen.add(key)

        results.append(
            f"{name} ({degree})"
        )

    return results


# ======================================================================
# RESPOSTAS
# ======================================================================


def direct_official_answer(
    question: str,
) -> Optional[str]:

    route = detect_direct_intent(
        question
    )

    if route is None:
        return None


    # ------------------------------------------------------------------
    # REGULAMENTO DA GRADUAÇÃO
    # ------------------------------------------------------------------

    if route == "graduation_regulation":

        return (
            "O Regulamento do Ensino de Graduação da UFPA estabelece "
            "as normas gerais para a organização do ensino de graduação. "
            "Entre os temas abrangidos estão princípios da formação, "
            "estrutura curricular, oferta acadêmica, atividades curriculares, "
            "pesquisa e extensão como estratégias de formação, avaliação "
            "e procedimentos da vida acadêmica. "
            "O regulamento foi aprovado pela Resolução CONSEPE nº 4.399/2013. "
            "Para uma dúvida específica, como matrícula, aproveitamento de estudos, "
            "trancamento ou avaliação, informe o tema para que a Minerva localize "
            "a regra correspondente. "
            f"Fonte oficial: {URL_GRAD_REGULATION_PAGE} "
            f"| Resolução: {URL_GRAD_REGULATION_PDF}"
        )


    # ------------------------------------------------------------------
    # REGIMENTO GERAL
    # ------------------------------------------------------------------

    if route == "general_regiment":

        return (
            "O Regimento Geral da Universidade Federal do Pará é um dos "
            "documentos institucionais que disciplinam a organização e o "
            "funcionamento da Universidade, incluindo competências e relações "
            "entre seus órgãos e estruturas acadêmicas e administrativas. "
            "O documento oficial é associado à Resolução nº 616/2006. "
            f"Documento oficial: {URL_GENERAL_REGIMENT_PDF} "
            f"| Página de legislação da UFPA: {URL_UFPA_LEGISLATION}"
        )


    # ------------------------------------------------------------------
    # ESTATUTO
    # ------------------------------------------------------------------

    if route == "ufpa_statute":

        return (
            "O Estatuto da UFPA é o documento institucional que estabelece "
            "as bases fundamentais da organização da Universidade. "
            "A página oficial de legislação da UFPA disponibiliza o Estatuto "
            "e o Regimento Geral para consulta. "
            f"Fonte oficial: {URL_UFPA_LEGISLATION}"
        )


    # ------------------------------------------------------------------
    # IDENTIDADE UFPA
    # ------------------------------------------------------------------

    if route == "ufpa_identity":

        return (
            "UFPA significa Universidade Federal do Pará, "
            "instituição federal de ensino superior. "
            "Essa resposta é usada apenas quando a pergunta solicita "
            "explicitamente o significado da sigla."
        )


    # ------------------------------------------------------------------
    # IDENTIDADE FCT
    # ------------------------------------------------------------------

    if route == "fct_identity":

        return (
            "A FCT é a Faculdade de Engenharia da Computação "
            "e Telecomunicações da Universidade Federal do Pará. "
            f"Fonte oficial: {URL_FCT_ABOUT}"
        )


    # ------------------------------------------------------------------
    # CURSOS
    # ------------------------------------------------------------------

    if route == "courses":

        text = _normalize(
            _page_text(
                URL_FCT_ABOUT
            )
        )

        courses: List[str] = []

        if (
            "engenharia da computacao"
            in text
        ):
            courses.append(
                "Engenharia da Computação"
            )

        if (
            "engenharia de telecomunicacoes"
            in text
        ):
            courses.append(
                "Engenharia de Telecomunicações"
            )

        if courses:
            return (
                "A FCT/UFPA oferece os cursos de "
                + " e ".join(courses)
                + ". "
                + f"Fonte oficial: {URL_FCT_ABOUT}"
            )

        return (
            "As informações oficiais sobre os cursos da FCT "
            "estão disponíveis na página institucional da faculdade. "
            f"Fonte oficial: {URL_FCT_ABOUT}"
        )


    # ------------------------------------------------------------------
    # DIREÇÃO
    # ------------------------------------------------------------------

    if route == "leadership":

        text = (
            _page_text(
                URL_FCT_CONTACT
            )
            or
            _page_text(
                URL_FCT_ABOUT
            )
        )

        director = _label_value(
            text,
            ["Diretor"],
        )

        vice = _label_value(
            text,
            [
                "Vice-Diretor",
                "Vice Diretor",
                "Vice-diretor",
            ],
        )

        q = _normalize(question)

        if "vice" in q:

            if vice:
                return (
                    f"O vice-diretor da FCT/UFPA é {vice}. "
                    f"Fonte oficial: {URL_FCT_CONTACT}"
                )

        if director:
            return (
                f"O diretor da FCT/UFPA é {director}. "
                f"Fonte oficial: {URL_FCT_CONTACT}"
            )

        return (
            "A informação atual sobre a direção deve ser consultada "
            "na página oficial de contato da FCT/UFPA. "
            f"Fonte oficial: {URL_FCT_CONTACT}"
        )


    # ------------------------------------------------------------------
    # DOCENTES
    # ------------------------------------------------------------------

    if route == "faculty":

        text = _page_text(
            URL_FCT_FACULTY
        )

        faculty = _faculty_list(
            text
        )

        if faculty:
            return (
                "Segundo a página oficial de Corpo Docente da FCT/UFPA, "
                "os docentes listados são: "
                + "; ".join(faculty)
                + ". "
                + f"Fonte oficial: {URL_FCT_FACULTY}"
            )

        return (
            "A lista institucional de professores está disponível "
            "na página oficial de Corpo Docente da FCT/UFPA. "
            f"Fonte oficial: {URL_FCT_FACULTY}"
        )


    # ------------------------------------------------------------------
    # CONTATO
    # ------------------------------------------------------------------

    if route == "contact":

        text = _page_text(
            URL_FCT_CONTACT
        )

        phone = _label_value(
            text,
            ["Telefone"],
        )

        email = _label_value(
            text,
            ["E-mail", "Email"],
        )

        parts: List[str] = []

        if email:
            parts.append(
                f"e-mail {email}"
            )

        if phone:
            parts.append(
                f"telefone {phone}"
            )

        if parts:
            return (
                "Os dados oficiais de contato localizados são: "
                + "; ".join(parts)
                + ". "
                + f"Fonte oficial: {URL_FCT_CONTACT}"
            )

        return (
            "Os dados institucionais de contato da FCT estão "
            "na página oficial de contato. "
            f"Fonte oficial: {URL_FCT_CONTACT}"
        )


    # ------------------------------------------------------------------
    # TCC
    # ------------------------------------------------------------------

    if route == "tcc":

        return (
            "Para TCC, a Minerva deve priorizar a documentação específica "
            "da FCT e as normas gerais de graduação da UFPA. "
            "Quando a pergunta envolver regras institucionais gerais sobre "
            "Trabalho de Curso, a consulta deve considerar também as normas "
            "oficiais da PROEG. "
            f"Documentação FCT: {URL_FCT_DOCS} "
            f"| Legislação PROEG: {URL_PROEG_LEGISLATION}"
        )


    # ------------------------------------------------------------------
    # ESTÁGIO
    # ------------------------------------------------------------------

    if route == "internship":

        return (
            "As informações específicas sobre estágio na FCT devem ser "
            "consultadas primeiro na página oficial da faculdade. "
            "Para uma regra específica, como documentação, integralização, "
            "carga horária ou assinatura, a Minerva deve complementar a "
            "consulta com os documentos institucionais da base RAG. "
            f"Fonte oficial: {URL_FCT_INTERNSHIP}"
        )


    # ------------------------------------------------------------------
    # MATRÍCULA
    # ------------------------------------------------------------------

    if route == "enrollment":

        return (
            "Para matrícula e ajuste de matrícula, a Minerva deve verificar "
            "primeiro a orientação específica da FCT e, em seguida, as normas "
            "acadêmicas oficiais da UFPA e da PROEG. "
            f"Regulamento da Graduação: {URL_GRAD_REGULATION_PAGE}"
        )


    # ------------------------------------------------------------------
    # DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if route == "documentation":

        return (
            "A FCT possui uma seção oficial de Documentação. "
            "Formulários, requerimentos e documentos locais devem ser "
            "verificados primeiro nessa página; normas gerais da Universidade "
            "devem ser consultadas nos portais institucionais correspondentes. "
            f"Fonte oficial: {URL_FCT_DOCS}"
        )


    return None


def debug_direct_route(
    question: str,
) -> dict:

    return {
        "question": question,
        "intent": detect_direct_intent(
            question
        ),
    }


__all__ = [
    "detect_direct_intent",
    "direct_official_answer",
    "debug_direct_route",
]
