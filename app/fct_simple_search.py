from __future__ import annotations

import hashlib
import re
import time
import unicodedata

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen


# ============================================================
# MINERVA AI
# Recuperação oficial FCT/UFPA
#
# Somente Python stdlib:
# - sem requests
# - sem BeautifulSoup
# - sem pip
#
# Estratégia:
# 1. Detecta intenção
# 2. Prioriza página oficial específica
# 3. Extrai conteúdo estruturado
# 4. Faz fallback no portal
# 5. Nunca consulta domínio externo como evidência FCT
# ============================================================


FCT_BASE = "https://fct.ufpa.br/"
FCT_HOST = "fct.ufpa.br"

TIMEOUT = 10
CACHE_TTL = 15 * 60
MAX_CONTEXT_CHARS = 14000


# Páginas oficiais de alta prioridade.
OFFICIAL_PAGES: Dict[str, str] = {
    "inicio": (
        "https://fct.ufpa.br/"
    ),
    "corpo_docente": (
        "https://fct.ufpa.br/index.php/corpo-docente"
    ),
    "contato": (
        "https://fct.ufpa.br/index.php/contato"
    ),
    "sobre": (
        "https://fct.ufpa.br/index.php/sobre-a-faculdade"
    ),
    "documentacao": (
        "https://fct.ufpa.br/index.php/documentacao"
    ),
    "historico": (
        "https://fct.ufpa.br/index.php/historico"
    ),
    "planos_disciplinas": (
        "https://fct.ufpa.br/index.php/plano-da-disciplina"
    ),
    "guia_calouros": (
        "https://fct.ufpa.br/index.php/guia-para-os-calouros-da-fct"
    ),
}


_CACHE: Dict[str, Tuple[float, str]] = {}


STOPWORDS = {
    "a", "o", "as", "os",
    "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos",
    "em", "na", "no", "nas", "nos",
    "para", "por", "com", "sem",
    "sobre", "entre",
    "e", "ou",
    "que", "qual", "quais",
    "como", "onde", "quando", "quem",
    "me", "se",
    "ao", "aos",
    "pela", "pelo",
    "tem", "ter",
    "ser", "sao",
    "isso", "essa", "esse",
    "esta", "este",
}


@dataclass(frozen=True)
class Evidence:
    score: float
    text: str
    url: str
    title: str


def normalize(text: str) -> str:
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


def tokens(text: str) -> List[str]:
    return [
        token
        for token in re.findall(
            r"[a-z0-9]{2,}",
            normalize(text),
        )
        if token not in STOPWORDS
    ]


def official_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        host = (
            parsed.hostname
            or ""
        ).lower()

        scheme = (
            parsed.scheme
            or ""
        ).lower()

        return (
            scheme in {"http", "https"}
            and (
                host == FCT_HOST
                or host.endswith(
                    "." + FCT_HOST
                )
            )
        )

    except Exception:
        return False


# ============================================================
# CLASSIFICAÇÃO DE INTENÇÃO
# ============================================================


def detect_intent(question: str) -> str:
    q = normalize(question)
    qset = set(tokens(q))

    # RU/PROAES deve continuar fora da rota FCT.
    if (
        "ru" in qset
        or "cardapio" in qset
        or "proaes" in qset
        or "bandejao" in qset
        or "restaurante universitario" in q
    ):
        return "external_special_route"

    if any(
        term in q
        for term in (
            "professor",
            "professores",
            "docente",
            "docentes",
            "corpo docente",
            "quem ensina",
        )
    ):
        return "corpo_docente"

    if any(
        term in q
        for term in (
            "diretor",
            "diretora",
            "vice diretor",
            "vice-diretor",
            "direcao",
            "coordenador",
            "coordenadora",
            "coordenacao",
        )
    ):
        return "direcao"

    if any(
        term in q
        for term in (
            "telefone",
            "contato",
            "email",
            "e-mail",
            "endereco",
            "localizacao",
            "onde fica",
            "secretaria",
        )
    ):
        return "contato"

    if any(
        term in q
        for term in (
            "quais cursos",
            "curso oferece",
            "cursos oferece",
            "engenharia da computacao",
            "engenharia de telecomunicacoes",
            "sobre a faculdade",
            "o que e fct",
            "o que significa fct",
            "significa fct",
        )
    ):
        return "sobre"

    if any(
        term in q
        for term in (
            "documento",
            "documentos",
            "documentacao",
            "formulario",
            "formularios",
        )
    ):
        return "documentacao"

    if any(
        term in q
        for term in (
            "historia",
            "historico",
            "quando surgiu",
            "quando foi criada",
            "fundacao",
        )
    ):
        return "historico"

    if any(
        term in q
        for term in (
            "plano de disciplina",
            "planos de disciplina",
            "ementa",
            "disciplinas",
        )
    ):
        return "planos_disciplinas"

    if any(
        term in q
        for term in (
            "calouro",
            "calouros",
            "guia",
            "como se matricular",
            "matricula",
            "matricular",
        )
    ):
        return "guia_calouros"

    return "geral"


def is_simple_fct_question(
    question: str,
) -> bool:
    if not isinstance(
        question,
        str,
    ):
        return False

    if not question.strip():
        return False

    intent = detect_intent(
        question
    )

    if intent == "external_special_route":
        return False

    q = normalize(question)

    complex_terms = (
        "analise comparativa",
        "fundamentacao juridica",
        "interpretacao normativa",
        "jurisprudencia",
        "calculo detalhado",
    )

    if any(
        term in q
        for term in complex_terms
    ):
        return False

    # Perguntas institucionais curtas e médias.
    return len(q.split()) <= 35


# ============================================================
# PARSER HTML
# ============================================================


class PortalParser(HTMLParser):
    SKIP_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
    }

    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.skip_depth = 0

        self.pieces: List[str] = []
        self.links: List[
            Tuple[str, str]
        ] = []

        self._current_href: Optional[str] = None
        self._anchor_parts: List[str] = []

        self._in_title = False
        self._title_parts: List[str] = []


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

        if tag == "title":
            self._in_title = True

        if tag == "a":
            attrs_dict = dict(attrs)

            self._current_href = (
                attrs_dict.get("href")
            )

            self._anchor_parts = []


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

        if tag == "title":
            self._in_title = False

        if tag == "a":
            if self._current_href:
                anchor = re.sub(
                    r"\s+",
                    " ",
                    " ".join(
                        self._anchor_parts
                    ),
                ).strip()

                self.links.append(
                    (
                        self._current_href,
                        anchor,
                    )
                )

            self._current_href = None
            self._anchor_parts = []


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

        self.pieces.append(text)

        if self._in_title:
            self._title_parts.append(
                text
            )

        if self._current_href is not None:
            self._anchor_parts.append(
                text
            )


    @property
    def title(self) -> str:
        return re.sub(
            r"\s+",
            " ",
            " ".join(
                self._title_parts
            ),
        ).strip()


def parse_html(
    html: str,
) -> PortalParser:
    parser = PortalParser()

    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # HTML imperfeito não derruba a Minerva.
        pass

    return parser


# ============================================================
# HTTP
# ============================================================


def fetch(
    url: str,
) -> Optional[str]:
    if not official_url(url):
        return None

    request = Request(
        url,
        headers={
            "User-Agent": (
                "MinervaAI-FCT-UFPA/2.0 "
                "(consulta institucional)"
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

            if not official_url(
                final_url
            ):
                return None

            raw = response.read()

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            try:
                return raw.decode(
                    charset,
                    errors="replace",
                )
            except LookupError:
                return raw.decode(
                    "utf-8",
                    errors="replace",
                )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
    ):
        return None


# ============================================================
# CACHE
# ============================================================


def cache_get(
    key: str,
) -> Optional[str]:
    item = _CACHE.get(key)

    if item is None:
        return None

    created, value = item

    if (
        time.time() - created
        > CACHE_TTL
    ):
        _CACHE.pop(
            key,
            None,
        )
        return None

    return value


def cache_set(
    key: str,
    value: str,
) -> None:
    _CACHE[key] = (
        time.time(),
        value,
    )


# ============================================================
# EXTRAÇÃO ESTRUTURADA: CORPO DOCENTE
# ============================================================


def extract_faculty(
    parser: PortalParser,
    url: str,
) -> Optional[str]:
    # Une os fragmentos mantendo quebras.
    text = "\n".join(
        parser.pieces
    )

    # Exemplo real:
    # ADALBERY RODRIGUES CASTRO (DOUTOR)
    pattern = re.compile(
        r"(?m)"
        r"^"
        r"([A-ZÀ-ÖØ-Ý]"
        r"[A-ZÀ-ÖØ-Ý0-9 .'\-]{3,120})"
        r"\s*"
        r"\("
        r"(DOUTOR|DOUTORA|MESTRE|MESTRA)"
        r"\)"
        r"\s*$"
    )

    found: List[
        Tuple[str, str]
    ] = []

    seen = set()

    for match in pattern.finditer(
        text
    ):
        name = re.sub(
            r"\s+",
            " ",
            match.group(1),
        ).strip()

        degree = match.group(2)

        key = normalize(name)

        if key in seen:
            continue

        seen.add(key)

        found.append(
            (
                name,
                degree,
            )
        )

    if not found:
        return None

    lines = [
        "CORPO DOCENTE DA FCT/UFPA:",
    ]

    for name, degree in found:
        lines.append(
            f"- {name} ({degree})"
        )

    lines.extend(
        [
            "",
            f"Fonte oficial: {url}",
        ]
    )

    return "\n".join(lines)


# ============================================================
# EXTRAÇÃO ESTRUTURADA: DIREÇÃO / CONTATO
# ============================================================


def extract_direction_contact(
    parser: PortalParser,
    url: str,
) -> Optional[str]:
    text = "\n".join(
        parser.pieces
    )

    labels = (
        "Diretor",
        "Vice-Diretor",
        "Vice-diretor",
        "Coordenador do Curso de Eng. da Computação",
        "Coordenador do Curso de Eng. de Telecomunicações",
        "Secretaria",
        "Secretário",
        "Secretária",
        "E-mail",
        "Telefone",
        "Localização",
    )

    results: List[str] = []
    seen = set()

    for label in labels:
        pattern = re.compile(
            rf"(?im)"
            rf"{re.escape(label)}"
            rf"\s*:\s*"
            rf"([^\n]+)"
        )

        for match in pattern.finditer(
            text
        ):
            value = re.sub(
                r"\s+",
                " ",
                match.group(1),
            ).strip()

            line = (
                f"{label}: {value}"
            )

            key = normalize(line)

            if key in seen:
                continue

            seen.add(key)
            results.append(line)

    if not results:
        return None

    return (
        "DADOS OFICIAIS DA FCT/UFPA:\n"
        + "\n".join(
            f"- {line}"
            for line in results
        )
        + "\n\n"
        + f"Fonte oficial: {url}"
    )


# ============================================================
# BUSCA POR TRECHOS
# ============================================================


def semantic_terms(
    question: str,
) -> set[str]:
    qset = set(
        tokens(question)
    )

    q = normalize(question)

    expansions: Dict[str, set[str]] = {
        "professor": {
            "professor",
            "docente",
            "doutor",
            "mestre",
        },
        "professores": {
            "professor",
            "docente",
            "doutor",
            "mestre",
        },
        "diretor": {
            "diretor",
            "direcao",
            "faculdade",
        },
        "curso": {
            "curso",
            "graduacao",
            "engenharia",
        },
        "cursos": {
            "curso",
            "graduacao",
            "engenharia",
        },
        "matricula": {
            "matricula",
            "calouro",
            "sigaa",
        },
        "matricular": {
            "matricula",
            "calouro",
            "sigaa",
        },
    }

    for word, additions in expansions.items():
        if word in q:
            qset.update(
                additions
            )

    return qset


def build_windows(
    pieces: Sequence[str],
) -> Iterable[str]:
    cleaned = [
        re.sub(
            r"\s+",
            " ",
            piece,
        ).strip()
        for piece in pieces
        if piece.strip()
    ]

    # Trechos individuais.
    for piece in cleaned:
        if 25 <= len(piece) <= 2000:
            yield piece

    # Janelas contextuais.
    for size in (2, 3, 5):
        for i in range(
            0,
            max(
                0,
                len(cleaned) - size + 1,
            ),
        ):
            block = " ".join(
                cleaned[
                    i:i + size
                ]
            )

            if (
                40
                <= len(block)
                <= 2500
            ):
                yield block


def score_text(
    question: str,
    text: str,
) -> float:
    qset = semantic_terms(
        question
    )

    tset = set(
        tokens(text)
    )

    overlap = len(
        qset & tset
    )

    coverage = (
        overlap
        / max(
            1,
            len(qset),
        )
    )

    score = (
        overlap * 8.0
        + coverage * 14.0
    )

    normalized_text = normalize(
        text
    )

    # Correspondência de expressão.
    normalized_question = normalize(
        question
    )

    for phrase in (
        "corpo docente",
        "direcao da faculdade",
        "engenharia da computacao",
        "engenharia de telecomunicacoes",
        "secretaria",
        "telefone",
        "contato",
    ):
        if (
            phrase in normalized_question
            and phrase in normalized_text
        ):
            score += 18.0

    return score


def generic_evidence(
    question: str,
    parser: PortalParser,
    url: str,
) -> List[Evidence]:
    title = (
        parser.title
        or "FCT/UFPA"
    )

    evidence: List[Evidence] = []

    seen = set()

    for block in build_windows(
        parser.pieces
    ):
        fingerprint = normalize(
            block
        )[:900]

        if fingerprint in seen:
            continue

        seen.add(fingerprint)

        score = score_text(
            question,
            block,
        )

        if score <= 0:
            continue

        evidence.append(
            Evidence(
                score=score,
                text=block,
                url=url,
                title=title,
            )
        )

    return evidence


# ============================================================
# DESCOBRIR LINKS INTERNOS
# ============================================================


def discover_internal_links(
    question: str,
    parser: PortalParser,
    source_url: str,
) -> List[Tuple[float, str]]:
    qset = semantic_terms(
        question
    )

    found: Dict[str, float] = {}

    for href, anchor in parser.links:
        if not href:
            continue

        absolute = urljoin(
            source_url,
            href,
        ).split(
            "#",
            1,
        )[0]

        if not official_url(
            absolute
        ):
            continue

        material = (
            anchor
            + " "
            + absolute
        )

        material_tokens = set(
            tokens(material)
        )

        overlap = len(
            qset & material_tokens
        )

        score = overlap * 8.0

        useful = (
            "docente",
            "professor",
            "contato",
            "faculdade",
            "curso",
            "graduacao",
            "disciplina",
            "estagio",
            "secretaria",
            "documentacao",
            "historico",
            "laboratorio",
        )

        normalized_material = normalize(
            material
        )

        if any(
            term in normalized_material
            for term in useful
        ):
            score += 2.0

        current = found.get(
            absolute
        )

        if (
            current is None
            or score > current
        ):
            found[absolute] = score

    return sorted(
        (
            (score, url)
            for url, score in found.items()
        ),
        key=lambda item: item[0],
        reverse=True,
    )


# ============================================================
# ROTEAMENTO DAS PÁGINAS
# ============================================================


def priority_urls(
    question: str,
) -> List[str]:
    intent = detect_intent(
        question
    )

    mapping = {
        "corpo_docente": [
            OFFICIAL_PAGES["corpo_docente"],
        ],

        "direcao": [
            OFFICIAL_PAGES["contato"],
            OFFICIAL_PAGES["sobre"],
        ],

        "contato": [
            OFFICIAL_PAGES["contato"],
            OFFICIAL_PAGES["sobre"],
        ],

        "sobre": [
            OFFICIAL_PAGES["sobre"],
        ],

        "documentacao": [
            OFFICIAL_PAGES["documentacao"],
        ],

        "historico": [
            OFFICIAL_PAGES["historico"],
        ],

        "planos_disciplinas": [
            OFFICIAL_PAGES["planos_disciplinas"],
        ],

        "guia_calouros": [
            OFFICIAL_PAGES["guia_calouros"],
            OFFICIAL_PAGES["sobre"],
        ],

        "geral": [
            OFFICIAL_PAGES["inicio"],
            OFFICIAL_PAGES["sobre"],
        ],
    }

    return mapping.get(
        intent,
        [
            OFFICIAL_PAGES["inicio"],
        ],
    )


# ============================================================
# BUSCA PRINCIPAL
# ============================================================


def search_fct_context(
    question: str,
) -> str:
    if not isinstance(
        question,
        str,
    ):
        return ""

    if not question.strip():
        return ""

    intent = detect_intent(
        question
    )

    if intent == "external_special_route":
        return ""

    cache_key = hashlib.sha256(
        normalize(question).encode(
            "utf-8"
        )
    ).hexdigest()

    cached = cache_get(
        cache_key
    )

    if cached is not None:
        return cached

    urls: List[str] = []

    # 1. Páginas exatas pela intenção.
    urls.extend(
        priority_urls(
            question
        )
    )

    # 2. Página inicial para descoberta.
    if OFFICIAL_PAGES["inicio"] not in urls:
        urls.append(
            OFFICIAL_PAGES["inicio"]
        )

    # 3. Busca interna Joomla como fallback.
    search_url = (
        FCT_BASE
        + "index.php/component/search/"
        + "?searchword="
        + quote_plus(question)
        + "&searchphrase=all"
    )

    urls.append(
        search_url
    )

    fetched: Dict[
        str,
        PortalParser
    ] = {}

    # Primeira rodada.
    for url in urls:
        if url in fetched:
            continue

        html = fetch(url)

        if not html:
            continue

        fetched[url] = parse_html(
            html
        )

    # 4. Descoberta de links internos.
    discovered: Dict[
        str,
        float
    ] = {}

    for source_url, parser in fetched.items():
        for score, link in discover_internal_links(
            question,
            parser,
            source_url,
        ):
            discovered[link] = max(
                score,
                discovered.get(
                    link,
                    float("-inf"),
                ),
            )

    # Busca apenas poucos links mais relevantes.
    for url, _score in sorted(
        discovered.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:6]:

        if url in fetched:
            continue

        html = fetch(url)

        if html:
            fetched[url] = parse_html(
                html
            )

    # ========================================================
    # EXTRAÇÕES DIRETAS
    # ========================================================

    direct_blocks: List[str] = []

    if intent == "corpo_docente":
        url = OFFICIAL_PAGES[
            "corpo_docente"
        ]

        parser = fetched.get(
            url
        )

        if parser:
            direct = extract_faculty(
                parser,
                url,
            )

            if direct:
                direct_blocks.append(
                    direct
                )

    if intent in {
        "direcao",
        "contato",
    }:
        for url in (
            OFFICIAL_PAGES["contato"],
            OFFICIAL_PAGES["sobre"],
        ):
            parser = fetched.get(
                url
            )

            if not parser:
                continue

            direct = extract_direction_contact(
                parser,
                url,
            )

            if direct:
                direct_blocks.append(
                    direct
                )

    # ========================================================
    # EVIDÊNCIAS GENÉRICAS
    # ========================================================

    all_evidence: List[Evidence] = []

    for url, parser in fetched.items():
        all_evidence.extend(
            generic_evidence(
                question,
                parser,
                url,
            )
        )

    # Deduplicar.
    unique: Dict[
        str,
        Evidence
    ] = {}

    for item in all_evidence:
        fingerprint = normalize(
            item.text
        )[:900]

        current = unique.get(
            fingerprint
        )

        if (
            current is None
            or item.score
            > current.score
        ):
            unique[
                fingerprint
            ] = item

    ranked = sorted(
        unique.values(),
        key=lambda item: item.score,
        reverse=True,
    )[:8]

    blocks: List[str] = []

    # Evidências estruturadas vêm primeiro.
    blocks.extend(
        direct_blocks
    )

    for index, item in enumerate(
        ranked,
        start=1,
    ):
        blocks.append(
            "\n".join(
                [
                    f"[EVIDENCIA FCT {index}]",
                    f"Titulo: {item.title}",
                    f"Trecho: {item.text}",
                    f"Fonte oficial: {item.url}",
                ]
            )
        )

    if not blocks:
        cache_set(
            cache_key,
            "",
        )
        return ""

    result_parts: List[str] = []

    total_chars = 0

    for block in blocks:
        if (
            total_chars + len(block)
            > MAX_CONTEXT_CHARS
        ):
            break

        result_parts.append(
            block
        )

        total_chars += len(
            block
        )

    result = "\n\n".join(
        result_parts
    ).strip()

    cache_set(
        cache_key,
        result,
    )

    return result


# ============================================================
# INTEGRAÇÃO COM PIPELINE EXISTENTE
# ============================================================


def augment_simple_fct_question(
    question: str,
) -> str:
    if not isinstance(
        question,
        str,
    ):
        return question

    if not is_simple_fct_question(
        question
    ):
        return question

    intent = detect_intent(
        question
    )

    if intent == "external_special_route":
        return question

    context = search_fct_context(
        question
    )

    if not context:
        # Não bloqueia RAG atual.
        return question

    return f"""
[ROTEAMENTO OFICIAL FCT/UFPA]

INTENCAO DETECTADA:
{intent}

PERGUNTA ORIGINAL:
{question}

EVIDENCIAS OFICIAIS RECUPERADAS:
{context}

INSTRUCOES OBRIGATORIAS PARA A RESPOSTA:
1. Responda exatamente a pergunta original.
2. Use primeiro as evidencias oficiais acima.
3. FCT significa Faculdade de Engenharia da Computacao e Telecomunicacoes da UFPA.
4. Para perguntas sobre professores, use a evidencia da pagina Corpo Docente.
5. Para perguntas sobre Diretor, Vice-Diretor ou coordenacao, use Contato ou Sobre a Faculdade.
6. Nao responda apenas o significado de FCT quando a pergunta pedir uma pessoa, cargo, curso, telefone ou lista.
7. Nao invente nomes, cargos, datas, contatos ou procedimentos.
8. Responda em portugues do Brasil.
9. Seja direto.
10. Ao final, informe a fonte oficial utilizada.
11. Ignore fontes externas quando houver evidencia oficial da FCT.
12. Preserve a rota PROAES para RU e cardapio.

Agora responda somente a PERGUNTA ORIGINAL.
""".strip()


__all__ = [
    "detect_intent",
    "is_simple_fct_question",
    "search_fct_context",
    "augment_simple_fct_question",
]
