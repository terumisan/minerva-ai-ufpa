from __future__ import annotations

import re
import time
import unicodedata

from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


# ======================================================================
# MINERVA AI
# BASE DE INFORMAÇÕES BÁSICAS E SIGLAS
#
# Estratégia:
#
# 1. Base oficial conhecida
# 2. Relações institucionais conhecidas
# 3. Busca dinâmica nos portais oficiais
# 4. Nunca inventar expansão de sigla
#
# Prioridade:
# FCT -> ITEC -> PPGEE -> UFPA -> unidades oficiais
# ======================================================================


# ----------------------------------------------------------------------
# PORTAIS OFICIAIS
# ----------------------------------------------------------------------

FCT_HOME = (
    "https://fct.ufpa.br/"
)

FCT_SOBRE = (
    "https://fct.ufpa.br/index.php/sobre-a-faculdade"
)

FCT_CONTATO = (
    "https://fct.ufpa.br/index.php/contato"
)

ITEC_HOME = (
    "https://itec.ufpa.br/index.php?lang=pt"
)

ITEC_FACULDADES = (
    "https://www.itec.ufpa.br/"
    "index.php?Itemid=315&id=74&lang=pt"
    "&option=com_content&view=category"
)

PPGEE_HOME = (
    "https://www.ppgee.propesp.ufpa.br/index.php/br/"
)

PPGEE_APRESENTACAO = (
    "https://ppgee.propesp.ufpa.br/"
    "index.php/br/programa/apresentacao"
)

UFPA_HOME = (
    "https://ufpa.br/"
)

UFPA_FCT_ORGAO = (
    "https://ufpa.br/orgaos/"
    "faculdade-de-engenharia-da-computacao-e-telecomunicacoes/"
)

PROEG_HOME = (
    "https://proeg.ufpa.br/"
)

PROAES_HOME = (
    "https://proaes.ufpa.br/"
)

SIGAA_HOME = (
    "https://sigaa.ufpa.br/"
)

SAGITTA_HOME = (
    "https://sagitta.ufpa.br/sagitta/"
)


# ======================================================================
# BASE CONHECIDA
#
# Para FCT:
# - nome principal usado no projeto Minerva e no portal FCT;
# - alias institucional alternativo preservado.
# ======================================================================

BASIC_FACTS: Dict[
    str,
    dict,
] = {

    "UFPA": {
        "name": (
            "Universidade Federal do Pará"
        ),

        "description": (
            "instituição federal de ensino superior "
            "à qual pertencem as unidades e sistemas "
            "acadêmicos consultados pela Minerva"
        ),

        "sources": [
            UFPA_HOME,
        ],
    },


    "FCT": {
        "name": (
            "Faculdade de Computação e Telecomunicações"
        ),

        "description": (
            "faculdade da UFPA vinculada ao contexto "
            "acadêmico do Instituto de Tecnologia"
        ),

        "aliases": [
            (
                "Faculdade de Engenharia da Computação "
                "e Telecomunicações"
            ),
        ],

        "note": (
            "A Minerva aceita também a forma "
            "“Faculdade de Engenharia da Computação "
            "e Telecomunicações”, encontrada em página "
            "institucional central da UFPA."
        ),

        "sources": [
            FCT_HOME,
            FCT_SOBRE,
            UFPA_FCT_ORGAO,
        ],
    },


    "ITEC": {
        "name": (
            "Instituto de Tecnologia"
        ),

        "description": (
            "instituto da Universidade Federal do Pará"
        ),

        "sources": [
            ITEC_HOME,
        ],
    },


    "PPGEE": {
        "name": (
            "Programa de Pós-Graduação em Engenharia Elétrica"
        ),

        "description": (
            "programa de pós-graduação da "
            "Universidade Federal do Pará"
        ),

        "sources": [
            PPGEE_APRESENTACAO,
            PPGEE_HOME,
        ],
    },


    "PROEG": {
        "name": (
            "Pró-Reitoria de Ensino de Graduação"
        ),

        "description": (
            "pró-reitoria da UFPA responsável por "
            "assuntos institucionais do ensino de graduação"
        ),

        "sources": [
            PROEG_HOME,
        ],
    },


    "PROAES": {
        "name": (
            "Pró-Reitoria de Assistência "
            "e Acessibilidade Estudantil"
        ),

        "description": (
            "pró-reitoria da UFPA relacionada "
            "à assistência e acessibilidade estudantil"
        ),

        "sources": [
            PROAES_HOME,
        ],
    },


    "SIGAA": {
        "name": (
            "Sistema Integrado de Gestão "
            "de Atividades Acadêmicas"
        ),

        "description": (
            "sistema acadêmico utilizado pela UFPA"
        ),

        "sources": [
            SIGAA_HOME,
        ],
    },


    "SAGITTA": {
        "name": (
            "Sistema de Atendimento ao Usuário da UFPA"
        ),

        "description": (
            "sistema institucional baseado em catálogo "
            "de serviços e solicitações de atendimento"
        ),

        "sources": [
            SAGITTA_HOME,
        ],
    },
}


# ======================================================================
# CONFIGURAÇÃO DA BUSCA DINÂMICA
# ======================================================================

OFFICIAL_ROOTS = [
    FCT_HOME,
    ITEC_HOME,
    PPGEE_HOME,
    UFPA_HOME,
    PROEG_HOME,
    PROAES_HOME,
    SIGAA_HOME,
    SAGITTA_HOME,
]


TIMEOUT = 7
CACHE_TTL = 15 * 60

MAX_DYNAMIC_PAGES = 10


_CACHE: Dict[
    str,
    Tuple[float, str],
] = {}


# ======================================================================
# NORMALIZAÇÃO
# ======================================================================

def _norm(text: str) -> str:

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
            _norm(text),
        )
    )


# ======================================================================
# DOMÍNIOS
# ======================================================================

def _official_ufpa_url(
    url: str,
) -> bool:

    try:

        parsed = urlparse(url)

        host = (
            parsed.hostname
            or ""
        ).lower().strip(".")

        return (
            parsed.scheme in {
                "http",
                "https",
            }
            and (
                host == "ufpa.br"
                or host.endswith(
                    ".ufpa.br"
                )
            )
        )

    except Exception:
        return False


# ======================================================================
# DETECÇÃO DE PERGUNTA BÁSICA
# ======================================================================

def _extract_acronym(
    question: str,
) -> Optional[str]:

    if not isinstance(
        question,
        str,
    ):
        return None

    original = question.strip()

    if not original:
        return None


    # ----------------------------------------------------------
    # Pergunta formada praticamente só pela sigla.
    # ----------------------------------------------------------

    compact = re.sub(
        r"[^A-Za-z0-9]",
        "",
        original,
    ).upper()

    if (
        2 <= len(compact) <= 12
        and compact in BASIC_FACTS
    ):
        return compact


    normalized = _norm(
        original
    )


    # ----------------------------------------------------------
    # Padrões explícitos.
    # ----------------------------------------------------------

    patterns = [

        (
            r"(?:o que significa|"
            r"qual o significado de|"
            r"qual e o significado de|"
            r"significado de|"
            r"sigla)"
            r"\s+"
            r"([a-z0-9]{2,12})"
            r"\b"
        ),

        (
            r"(?:o que e|quem e)"
            r"\s+"
            r"(?:a|o)?"
            r"\s*"
            r"([a-z0-9]{2,12})"
            r"\b"
        ),
    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            normalized,
        )

        if not match:
            continue

        candidate = (
            match.group(1)
            .upper()
        )

        if (
            2 <= len(candidate) <= 12
        ):
            return candidate


    return None


def classify_basic_question(
    question: str,
) -> Optional[str]:

    q = _norm(
        question
    )


    # ----------------------------------------------------------
    # Relação FCT / ITEC
    # ----------------------------------------------------------

    if (
        "fct" in _tokens(q)
        and "itec" in _tokens(q)
        and any(
            marker in q
            for marker in (
                "relacao",
                "vinculo",
                "vinculada",
                "vinculado",
                "pertence",
                "faz parte",
                "qual instituto",
            )
        )
    ):
        return "basic_relation_fct_itec"


    acronym = _extract_acronym(
        question
    )

    if acronym:
        return "basic_acronym"


    return None


# ======================================================================
# PARSER HTML
# ======================================================================

class _OfficialParser(HTMLParser):

    BLOCK_TAGS = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",

        "p",
        "li",
        "td",
        "th",
        "dt",
        "dd",
    }

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

        self.current_block: Optional[str] = None
        self.current_parts: List[str] = []

        self.current_href: Optional[str] = None
        self.current_anchor_parts: List[str] = []

        self.blocks: List[str] = []

        self.links: List[
            Tuple[str, str]
        ] = []


    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:

        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return


        if tag in self.BLOCK_TAGS:

            if self.current_block is not None:
                self._flush_block()

            self.current_block = tag
            self.current_parts = []


        if tag == "a":

            attrs_dict = dict(
                attrs
            )

            self.current_href = (
                attrs_dict.get(
                    "href"
                )
            )

            self.current_anchor_parts = []


    def handle_endtag(
        self,
        tag: str,
    ) -> None:

        tag = tag.lower()

        if tag in self.SKIP_TAGS:

            if self.skip_depth:
                self.skip_depth -= 1

            return


        if self.skip_depth:
            return


        if (
            self.current_block is not None
            and tag == self.current_block
        ):
            self._flush_block()


        if tag == "a":
            self._flush_anchor()


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

        if not text:
            return


        if self.current_block is not None:
            self.current_parts.append(
                text
            )


        if self.current_href is not None:
            self.current_anchor_parts.append(
                text
            )


    def close(self) -> None:

        self._flush_block()
        self._flush_anchor()

        super().close()


    def _flush_block(self) -> None:

        if self.current_block is None:
            return

        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                self.current_parts
            ),
        ).strip()

        if text:
            self.blocks.append(
                text
            )

        self.current_block = None
        self.current_parts = []


    def _flush_anchor(self) -> None:

        if self.current_href is None:
            return

        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                self.current_anchor_parts
            ),
        ).strip()

        self.links.append(
            (
                self.current_href,
                text,
            )
        )

        self.current_href = None
        self.current_anchor_parts = []


def _parse(
    html: str,
) -> _OfficialParser:

    parser = _OfficialParser()

    try:
        parser.feed(
            html
        )
        parser.close()

    except Exception:
        pass

    return parser


# ======================================================================
# HTTP
# ======================================================================

def _fetch(
    url: str,
) -> str:

    if not _official_ufpa_url(
        url
    ):
        return ""


    cached = _CACHE.get(
        url
    )

    if cached:

        created_at, content = cached

        if (
            time.time() - created_at
            <= CACHE_TTL
        ):
            return content


    request = Request(
        url,
        headers={
            "User-Agent": (
                "MinervaAI-UFPA-BasicFacts/1.0"
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

            if not _official_ufpa_url(
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


            _CACHE[url] = (
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


# ======================================================================
# BUSCA DINÂMICA DE SIGLA
# ======================================================================

def _clean_expansion(
    text: str,
) -> str:

    value = re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip(
        " \t\r\n-–—:;,.|"
    )

    # Evitar respostas absurdamente grandes.
    if len(value) > 180:
        value = value[:180].rsplit(
            " ",
            1,
        )[0]

    return value


def _extract_expansion_from_block(
    acronym: str,
    block: str,
) -> Optional[str]:

    escaped = re.escape(
        acronym
    )


    patterns = [

        # Universidade Federal do Pará (UFPA)
        (
            rf"([A-ZÀ-ÖØ-Ý]"
            rf"[A-Za-zÀ-ÿ0-9 ,.'’/\-–]{{4,170}}?)"
            rf"\s*\(\s*{escaped}\s*\)"
        ),

        # UFPA - Universidade Federal do Pará
        (
            rf"\b{escaped}\b"
            rf"\s*[-–—:]\s*"
            rf"([A-ZÀ-ÖØ-Ý]"
            rf"[A-Za-zÀ-ÿ0-9 ,.'’/\-–]{{4,170}})"
        ),

        # UFPA significa Universidade...
        (
            rf"\b{escaped}\b"
            rf"\s+(?:significa|é)\s+"
            rf"([A-ZÀ-ÖØ-Ý]"
            rf"[A-Za-zÀ-ÿ0-9 ,.'’/\-–]{{4,170}})"
        ),
    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            block,
            flags=re.I,
        )

        if not match:
            continue

        candidate = _clean_expansion(
            match.group(1)
        )

        if (
            4 <= len(candidate) <= 180
        ):
            return candidate


    return None


def _dynamic_search(
    acronym: str,
) -> Optional[
    Tuple[str, str]
]:

    pages: List[str] = []

    seen = set()


    # ----------------------------------------------------------
    # Primeiro: páginas raiz em prioridade.
    # ----------------------------------------------------------

    for root in OFFICIAL_ROOTS:

        if root not in seen:
            seen.add(root)
            pages.append(root)


    # ----------------------------------------------------------
    # Descobrir links que mencionam a sigla.
    # ----------------------------------------------------------

    discovered: List[str] = []


    for root in OFFICIAL_ROOTS[:4]:

        html = _fetch(
            root
        )

        if not html:
            continue

        parser = _parse(
            html
        )


        for href, anchor in parser.links:

            if not href:
                continue

            material = _norm(
                anchor
                + " "
                + href
            )

            if (
                acronym.lower()
                not in material
            ):
                continue

            absolute = urljoin(
                root,
                href,
            ).split(
                "#",
                1,
            )[0]

            if not _official_ufpa_url(
                absolute
            ):
                continue

            if absolute not in seen:
                seen.add(absolute)
                discovered.append(
                    absolute
                )


    pages.extend(
        discovered[:4]
    )


    # ----------------------------------------------------------
    # Procurar expansão.
    # ----------------------------------------------------------

    for url in pages[
        :MAX_DYNAMIC_PAGES
    ]:

        html = _fetch(
            url
        )

        if not html:
            continue

        parser = _parse(
            html
        )


        for block in parser.blocks:

            if (
                acronym.lower()
                not in block.lower()
            ):
                continue

            expansion = (
                _extract_expansion_from_block(
                    acronym,
                    block,
                )
            )

            if expansion:
                return (
                    expansion,
                    url,
                )


    return None


# ======================================================================
# RESPOSTAS
# ======================================================================

def _known_fact_answer(
    acronym: str,
) -> Optional[str]:

    fact = BASIC_FACTS.get(
        acronym
    )

    if not fact:
        return None


    name = str(
        fact.get(
            "name",
            "",
        )
    ).strip()

    description = str(
        fact.get(
            "description",
            "",
        )
    ).strip()

    note = str(
        fact.get(
            "note",
            "",
        )
    ).strip()

    sources = [
        str(source)
        for source in fact.get(
            "sources",
            [],
        )
    ]


    answer = (
        f"{acronym} significa {name}."
    )


    if description:
        answer += (
            f" No contexto da UFPA, trata-se de {description}."
        )


    if note:
        answer += (
            f" Observação: {note}"
        )


    if sources:
        answer += (
            " Fonte oficial: "
            + " | ".join(
                sources[:3]
            )
        )


    return answer


def basic_answer(
    question: str,
) -> Optional[str]:

    route = classify_basic_question(
        question
    )


    # ----------------------------------------------------------
    # Relação FCT / ITEC
    # ----------------------------------------------------------

    if (
        route
        == "basic_relation_fct_itec"
    ):

        return (
            "A FCT está vinculada ao contexto acadêmico do "
            "Instituto de Tecnologia da UFPA. O portal do ITEC "
            "mantém a área de faculdades e diretorias, enquanto "
            "a própria página de contato da FCT informa sua "
            "localização no ITEC. "
            f"Fontes oficiais: {ITEC_FACULDADES} "
            f"| {FCT_CONTATO}"
        )


    # ----------------------------------------------------------
    # Sigla
    # ----------------------------------------------------------

    if route == "basic_acronym":

        acronym = _extract_acronym(
            question
        )

        if not acronym:
            return None


        # 1. Base conhecida.
        known = _known_fact_answer(
            acronym
        )

        if known:
            return known


        # 2. Busca dinâmica oficial.
        dynamic = _dynamic_search(
            acronym
        )

        if dynamic:

            expansion, source = dynamic

            return (
                f"No contexto dos portais oficiais da UFPA, "
                f"encontrei a associação da sigla {acronym} "
                f"com “{expansion}”. "
                f"Fonte oficial: {source}"
            )


        # 3. Permitir que o RAG/documentos atuais tentem responder.
        return None


    return None


def debug_basic(
    question: str,
) -> dict:

    return {
        "question": question,
        "route": classify_basic_question(
            question
        ),
        "acronym": _extract_acronym(
            question
        ),
        "answer": basic_answer(
            question
        ),
    }


__all__ = [
    "BASIC_FACTS",
    "classify_basic_question",
    "basic_answer",
    "debug_basic",
]
