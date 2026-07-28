from __future__ import annotations

import re
import time
import unicodedata

from datetime import datetime
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# ======================================================================
# MINERVA AI
#
# Roteador institucional prioritário.
#
# Objetivos:
# - responder as perguntas dos próprios botões;
# - FCT primeiro para assuntos locais;
# - UFPA oficial para assuntos gerais;
# - PROAES para cardápio;
# - PROEG para graduação;
# - não deixar atalhos genéricos de "FCT significa..." dominarem;
# - retornar None somente quando o RAG original deve continuar.
#
# Somente Python stdlib.
# Sem pip.
# Sem requests.
# Sem BeautifulSoup.
# ======================================================================


# ----------------------------------------------------------------------
# FONTES FCT
# ----------------------------------------------------------------------

FCT_HOME = "https://fct.ufpa.br/"

FCT_SOBRE = (
    "https://fct.ufpa.br/index.php/sobre-a-faculdade"
)

FCT_CONTATO = (
    "https://fct.ufpa.br/index.php/contato"
)

# Dados fixos de localização/telefone (perfil oficial da FCT no Google Maps,
# checado manually). A página FCT_CONTATO só expõe telefone/e-mail via
# _label_value — não tem endereço estruturado para extrair ao vivo, então
# esses dois campos abaixo ficam como valor conhecido, usados como
# complemento (endereço) e fallback (telefone) na rota "contact". Não inclui
# horário de funcionamento aqui: o horário do Google Maps é um status
# dinâmico ("Fechado · Abre qui. às 08:00" no momento da consulta), não um
# fato fixo — hardcodar ficaria errado em poucos dias.
FCT_ENDERECO = "Instituto de Tecnologia (ITEC), Universitário, Belém - PA"
FCT_TELEFONE_CONHECIDO = "(91) 3201-7901"

FCT_DOCENTES = (
    "https://fct.ufpa.br/index.php/corpo-docente"
)

FCT_DOCUMENTACAO = (
    "https://fct.ufpa.br/index.php/documentacao"
)

FCT_ESTAGIO = (
    "https://fct.ufpa.br/index.php/estagio"
)

# Guia do Mochileiro de EngComp: material feito pelo Centro Acadêmico
# (CAECOMP) para calouros, linkado pela página oficial da FCT abaixo.
FCT_GUIA_CALOURO = (
    "https://fct.ufpa.br/index.php/guia-para-os-calouros-da-fct"
)
GUIA_MOCHILEIRO_CAECOMP = "https://caecomp-ufpa.github.io/guia-fct/"

FCT_ATIVIDADES_COMPLEMENTARES = (
    "https://fct.ufpa.br/index.php/atividades-complementares"
)

FCT_HISTORICO = (
    "https://fct.ufpa.br/index.php/historico"
)

FCT_PLANOS = (
    "https://fct.ufpa.br/index.php/plano-da-disciplina"
)

FCT_TCC_RESOLUCAO = (
    "https://fct.ufpa.br/images/stories/"
    "Engcomp_Resolucao_TCC_2012.pdf"
)

FCT_REGIMENTO = (
    "https://www.fct.ufpa.br/images/stories/"
    "Regimento_FCT.pdf"
)


# ----------------------------------------------------------------------
# FONTES UFPA
# ----------------------------------------------------------------------

PROAES_CARDAPIO = (
    "https://proaes.ufpa.br/cardapio"
)

PROEG_REGULAMENTO = (
    "https://proeg.ufpa.br/index.php/"
    "regulamento-da-graduacao"
)

PROEG_LEGISLACAO = (
    "https://proeg.ufpa.br/legislacao1"
)

PROEG_TCC_2023 = (
    "https://proeg.ufpa.br/noticias/780-"
    "proeg-torna-publica-a-instrucao-normativa-"
    "que-regulamenta-o-trabalha-de-curso"
)

PROEG_CALENDARIO = (
    "https://proeg.ufpa.br/"
    "calendario-academico/62-academico/"
    "calendario-academico"
)

PROEG_GUIAS_MANUAIS = (
    "https://proeg.ufpa.br/guias-e-manuais"
)

PROEG_TUTORIAL_LABINFRA_MONITORIA = (
    "https://proeg.ufpa.br/images/Artigos/Academico/"
    "Guias-Manuais/Tutorial-de-execuo-2023-otimizado_1.pdf"
)

PROEG_SIGAA_DOCENTE = (
    "https://proeg.ufpa.br/images/Artigos/Academico/"
    "Guias-Manuais/SIgaaDocente2020.pdf"
)

PROEG_AVALIA_DISCENTE = (
    "https://proeg.ufpa.br/images/Artigos/Noticias/"
    "AVALIA_DISCENTE_ERE_ATUALIZAO_11-01-21.docx"
)

PROEG_AVALIA_DOCENTE = (
    "https://proeg.ufpa.br/images/Artigos/Noticias/"
    "AVALIA_DOCENTE_ERE_ATUALIZADO_11-01-2021-1.docx"
)

PROEG_LABINFRA_DESPESAS = (
    "https://proeg.ufpa.br/images/Artigos/Academico/"
    "Guias-Manuais/PROCEDIMENTOS-DE-SOLICITAO-FINAL--TODOS-LABINFRAS.pdf"
)

UFPA_LEGISLACAO = (
    "https://portal.ufpa.br/index.php/"
    "sig-ufpa/2-uncategorised/77-legislacao"
)

# Portal público do sistema acadêmico — mesmo sistema descrito no documento
# institucional "ManualAlunoSIGAA.pdf" já ingerido na base (ver rota
# "enrollment" abaixo).
SIGAA_URL = "https://sigaa.ufpa.br"


TIMEOUT = 10
CACHE_TTL = 15 * 60

_CACHE: Dict[str, Tuple[float, str]] = {}


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


def _has_any(
    text: str,
    markers: Sequence[str],
) -> bool:
    return any(
        marker in text
        for marker in markers
    )


# ======================================================================
# CLASSIFICAÇÃO
#
# A ORDEM É INTENCIONAL.
#
# Assuntos específicos vêm antes de:
#   "FCT significa..."
#   "UFPA significa..."
# ======================================================================

def classify_question(
    question: str,
) -> Optional[str]:

    if not isinstance(question, str):
        return None

    q = _norm(question)

    if not q:
        return None

    qset = _tokens(q)


    # ------------------------------------------------------------------
    # 0. OUTRAS UNIDADES DA UFPA (não-FCT)
    #
    # Bug real encontrado: "Qual a localização do CTIC?" caía na rota
    # "contact" (dispara em qualquer "localizacao"/"contato") e devolvia
    # o telefone/e-mail da FCT rotulado como se fosse do CTIC. As rotas
    # abaixo são todas específicas da FCT — se a pergunta menciona outra
    # unidade (CTIC, Reitoria, Biblioteca) sem também citar a FCT, nenhuma
    # rota fixa da FCT deve responder por ela.
    # ------------------------------------------------------------------

    if (
        _has_any(
            q,
            (
                "ctic",
                "reitoria",
                "biblioteca",
            ),
        )
        and not _has_any(
            q,
            (
                "fct",
                "faculdade de computacao",
                "faculdade de engenharia da computacao",
            ),
        )
    ):
        return None


    # ------------------------------------------------------------------
    # 1. CARDÁPIO
    # ------------------------------------------------------------------

    if (
        "cardapio" in qset
        or "bandejao" in qset
        or "restaurante universitario" in q
        or (
            "ru" in qset
            and _has_any(
                q,
                (
                    "hoje",
                    "almoco",
                    "jantar",
                    "cardapio",
                ),
            )
        )
    ):
        return "menu"


    # ------------------------------------------------------------------
    # 2. BANCA DE TCC
    # ------------------------------------------------------------------

    if (
        "tcc" in q
        and _has_any(
            q,
            (
                "banca",
                "membros",
                "examinadora",
                "defesa",
                "avaliadores",
                "avaliador",
            ),
        )
    ):
        return "tcc_board"


    # ------------------------------------------------------------------
    # 3. TCC GERAL
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "tcc",
            "trabalho de conclusao",
            "trabalho de curso",
        ),
    ):
        return "tcc"


    # ------------------------------------------------------------------
    # 4. ESTÁGIO
    # ------------------------------------------------------------------

    if "estagio" in q:
        return "internship"


    # ------------------------------------------------------------------
    # 4.5. MATRÍCULA
    #
    # Bug real (achado por medição de latência): "onde/como posso me
    # matricular" — uma das perguntas mais previsíveis e mais frequentes
    # que existem — não tinha NENHUMA rota fixa, então caía sempre no RAG
    # genérico (2-5min no Qwen2.5-7B em CPU) mesmo tendo resposta
    # institucional estável.
    #
    # Fraseado por frase (não "matricul" substring solto): um match
    # genérico demais interceptaria também perguntas específicas já
    # cobertas por entradas RESPOSTA_LITERAL do dataset (ex.: "O que
    # acontece após a solicitação de matrícula?", que tem resposta própria
    # mais detalhada em minerva_dataset.json) ANTES de chegarem lá — o
    # priority_router roda antes do dataset no pipeline (ver
    # priority_answer no fim do arquivo).
    # ------------------------------------------------------------------

    if (
        q in ("matricula", "matricular")
        or _has_any(
            q,
            (
                "onde posso me matricular",
                "como posso me matricular",
                "como faco para me matricular",
                "como faco minha matricula",
                "como faco a matricula",
                "onde faco a matricula",
                "onde faco minha matricula",
                "como e feita a matricula",
                "como funciona a matricula",
                "onde fica a matricula",
                "quero me matricular",
                "como me matriculo",
                "onde me matriculo",
                "como me matricular",
                "onde me matricular",
                "me matricular na ufpa",
                "me matricular na fct",
                "como se matricula",
                "como se faz a matricula",
                "onde se matricula",
                "onde e a matricula",
                # Encontrada por medição de latência real: "Quando posso me
                # matricular?" apareceu no histórico de conversas e não
                # batia em nenhuma frase acima (só cobria onde/como).
                "quando posso me matricular",
                "quando e a matricula",
                "quando comeca a matricula",
                "quando abre a matricula",
                "quando me matriculo",
            ),
        )
    ):
        return "enrollment"


    # ------------------------------------------------------------------
    # 4.6. TRANCAMENTO DE MATRÍCULA
    #
    # Encontrada varrendo os portais UFPA/FCT em busca de lacunas (mesma
    # técnica da rota "enrollment"): tema institucional estável, com regra
    # exata no Regulamento de Graduação (Art. 24), sem nenhuma rota fixa
    # até então — caía sempre no RAG genérico.
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "trancar matricula",
            "trancar a matricula",
            "trancar o curso",
            "trancar meu curso",
            "trancamento de matricula",
            "trancamento da matricula",
            "como faco para trancar",
            "quero trancar",
            "posso trancar",
        ),
    ):
        return "matricula_trancamento"


    # ------------------------------------------------------------------
    # 4.7. APROVEITAMENTO DE ESTUDOS
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "aproveitamento de estudos",
            "aproveitamento de disciplina",
            "aproveitamento de disciplinas",
            "equivalencia de disciplina",
            "equivalencia de disciplinas",
            "dispensa de disciplina",
            "dispensa de disciplinas",
            "como solicitar aproveitamento",
        ),
    ):
        return "aproveitamento_estudos"


    # ------------------------------------------------------------------
    # 4.8. GUIA DO CALOURO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "guia do calouro",
            "guia para calouros",
            "guia para os calouros",
            "guia do mochileiro",
            "sou calouro",
            "sou novato",
            "acabei de entrar na fct",
            "acabei de entrar na ufpa",
            "primeiro semestre o que preciso saber",
            "dicas para calouro",
            "dicas para calouros",
        ),
    ):
        return "guia_calouro"


    # ------------------------------------------------------------------
    # 4.9. ATIVIDADES COMPLEMENTARES
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "atividades complementares",
            "atividade complementar",
            "integralizar atividades complementares",
            "carga horaria de atividades complementares",
        ),
    ):
        return "atividades_complementares"


    # ------------------------------------------------------------------
    # 5. REGULAMENTO DA GRADUAÇÃO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "regulamento de graduacao",
            "regulamento da graduacao",
            "regulamento do ensino de graduacao",
            "regras da graduacao",
            "normas da graduacao",
        ),
    ):
        return "graduation_regulation"


    # ------------------------------------------------------------------
    # 6. REGIMENTO FCT
    # ------------------------------------------------------------------

    if (
        "regimento" in q
        and _has_any(
            q,
            (
                "fct",
                "faculdade",
            ),
        )
        and "geral da ufpa" not in q
    ):
        return "fct_regiment"


    # ------------------------------------------------------------------
    # 7. REGIMENTO GERAL UFPA
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "regimento geral da ufpa",
            "regimento geral ufpa",
            "regimento geral da universidade",
            "me mostre o regimento geral",
        ),
    ):
        return "ufpa_regiment"


    # ------------------------------------------------------------------
    # 7.5. GUIAS E MANUAIS DA PROEG (LabINFRA, Monitoria, AVALIA, portal
    # do docente no SIGAA). Verificado antes de "professores" porque
    # "docente" sozinho já dispara aquela rota (ex.: "avalia docente" e
    # "portal do docente" seriam capturados por engano como pergunta
    # sobre corpo docente).
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "labinfra",
            "bolsa monitoria",
            "avalia docente",
            "avalia discente",
            "portal do docente",
            "guias e manuais",
            "guias da proeg",
            "manuais da proeg",
        ),
    ):
        return "proeg_manuais"


    # ------------------------------------------------------------------
    # 8. PROFESSORES
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "professor",
            "professores",
            "docente",
            "docentes",
            "corpo docente",
        ),
    ):
        return "faculty"


    # ------------------------------------------------------------------
    # 9. DIREÇÃO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "diretor",
            "diretora",
            "vice diretor",
            "vice-diretor",
            "direcao",
            "quem dirige",
        ),
    ):
        return "leadership"


    # ------------------------------------------------------------------
    # 10. CURSOS
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "quais cursos",
            "cursos da fct",
            "cursos a fct",
            "cursos oferece",
            "curso oferece",
            "engenharia da computacao",
            "engenharia de telecomunicacoes",
        ),
    ):
        return "courses"


    # ------------------------------------------------------------------
    # 11. CONTATO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "telefone",
            "contato",
            "email",
            "e mail",
            "secretaria",
            "endereco",
            "localizacao",
            "onde fica a fct",
        ),
    ):
        return "contact"


    # ------------------------------------------------------------------
    # 12. CALENDÁRIO
    # ------------------------------------------------------------------

    if (
        q == "calendario"
        or _has_any(
            q,
            (
                "calendario academico",
                "quando comecam as aulas",
                "inicio das aulas",
                "fim do semestre",
                # Encontrada por medição de latência real: "quando começa
                # e termina o período letivo" apareceu 2x no histórico de
                # conversas e não batia em nenhuma frase acima.
                "quando comeca e termina o periodo letivo",
                "quando termina o periodo letivo",
                "quando comeca o periodo letivo",
                "inicio e fim do periodo letivo",
            ),
        )
    ):
        return "calendar"


    # ------------------------------------------------------------------
    # 13. REGRAS DOS DISCENTES
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "normas gerais se aplicam aos discentes",
            "normas para os discentes",
            "regras para os discentes",
            "direitos dos alunos",
            "deveres dos alunos",
        ),
    ):
        return "student_rules"


    # ------------------------------------------------------------------
    # 14. NORMAS FCT
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "normas fct",
            "regras da fct",
            "regras institucionais da faculdade",
            "normas institucionais da faculdade",
            "onde encontro as regras institucionais",
        ),
    ):
        return "fct_rules"


    # ------------------------------------------------------------------
    # 15. DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "documentacao",
            "documentos da fct",
            "formularios",
            "formulario",
            "requerimento",
        ),
    ):
        return "documentation"


    # ------------------------------------------------------------------
    # 16. PLANOS / EMENTAS
    # ------------------------------------------------------------------

    if _has_any(
        q,
        (
            "plano de disciplina",
            "planos de disciplina",
            "ementa",
            "ementas",
        ),
    ):
        return "discipline_plans"


    # ------------------------------------------------------------------
    # 17. IDENTIDADE FCT
    # Somente pergunta explicitamente sobre a sigla.
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
    # 18. IDENTIDADE UFPA
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
# HTML PARSER
# ======================================================================

class _PageParser(HTMLParser):

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


# ======================================================================
# HTTP
# ======================================================================

def _official_ufpa_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        host = (
            parsed.hostname
            or ""
        ).lower().strip(".")

        return (
            parsed.scheme in {"http", "https"}
            and (
                host == "ufpa.br"
                or host.endswith(".ufpa.br")
            )
        )

    except Exception:
        return False


def _fetch(url: str) -> str:

    if not _official_ufpa_url(url):
        return ""

    cached = _CACHE.get(url)

    if cached:
        created_at, value = cached

        if (
            time.time() - created_at
            <= CACHE_TTL
        ):
            return value

    request = Request(
        url,
        headers={
            "User-Agent": (
                "MinervaAI-UFPA/7.0 "
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
                value = raw.decode(
                    charset,
                    errors="replace",
                )

            except LookupError:
                value = raw.decode(
                    "utf-8",
                    errors="replace",
                )

            _CACHE[url] = (
                time.time(),
                value,
            )

            return value

    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
    ):
        return ""


def _page_pieces(url: str) -> List[str]:

    html = _fetch(url)

    if not html:
        return []

    parser = _PageParser()

    try:
        parser.feed(html)
        parser.close()

    except Exception:
        pass

    return parser.pieces


def _page_text(url: str) -> str:
    return "\n".join(
        _page_pieces(url)
    )


# ======================================================================
# EXTRAÇÃO AUXILIAR
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
        _norm(label)
        for label in labels
    }

    for index, line in enumerate(lines):

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
            _norm(line).rstrip(":")
            in normalized_labels
            and index + 1 < len(lines)
        ):
            candidate = lines[
                index + 1
            ].strip()

            if candidate:
                return candidate

    return None


def _faculty_list(text: str) -> List[str]:

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

        key = _norm(name)

        if key in seen:
            continue

        seen.add(key)

        results.append(
            f"{name} ({degree})"
        )

    return results


# ======================================================================
# CARDÁPIO DO DIA
# ======================================================================

_DATE_PATTERN = re.compile(
    r"\b"
    r"(0[1-9]|[12][0-9]|3[01])"
    r"/"
    r"(0[1-9]|1[0-2])"
    r"/"
    r"(20[0-9]{2})"
    r"\b"
)


def _menu_today() -> str:

    pieces = _page_pieces(
        PROAES_CARDAPIO
    )

    source = (
        f"Fonte oficial: {PROAES_CARDAPIO}"
    )

    if not pieces:
        return (
            "Não consegui consultar o cardápio oficial da PROAES "
            "neste momento. Para evitar informação incorreta, "
            "não vou inventar o menu. "
            + source
        )

    today = datetime.now().strftime(
        "%d/%m/%Y"
    )

    start = None

    for index, piece in enumerate(pieces):

        if today in piece:
            start = index
            break

    if start is None:
        return (
            f"Não localizei um cardápio publicado para hoje "
            f"({today}) na página oficial consultada. "
            + source
        )

    end = len(pieces)

    for index in range(
        start + 1,
        len(pieces),
    ):

        if _DATE_PATTERN.search(
            pieces[index]
        ):
            end = index
            break

    segment = [
        re.sub(
            r"\s+",
            " ",
            piece,
        ).strip()
        for piece in pieces[
            start:end
        ]
        if piece.strip()
    ]

    # Remover repetições consecutivas.
    cleaned: List[str] = []

    for value in segment:

        if (
            not cleaned
            or cleaned[-1] != value
        ):
            cleaned.append(value)

    # Limite defensivo.
    cleaned = cleaned[:70]

    if not cleaned:
        return (
            f"Não consegui interpretar o cardápio oficial de hoje "
            f"({today}). "
            + source
        )

    return (
        f"Cardápio oficial do RU para {today}: "
        + " | ".join(cleaned)
        + ". "
        + source
    )


# ======================================================================
# RESPOSTAS
# ======================================================================

# Bug real (achado analisando por que "Quem é a atual direção do FCT?"
# caía no RAG genérico apesar de a rota "leadership" abaixo cobrir
# "direcao"): o bloco MINERVA_BASIC_FACTS no fim do arquivo REBINDA o nome
# global "classify_question" para uma versão que checa siglas/fatos
# básicos primeiro. Como priority_answer() abaixo chama "classify_question"
# pelo nome (resolvido a cada chamada, não no momento da definição —
# late binding), depois que o rebind acontece, toda chamada aqui também
# passa pela checagem básica primeiro. Se essa checagem básica reivindica
# a pergunta (ex.: extrai "FCT" como sigla) mas falha ao gerar resposta
# (ex.: extração de sigla erra e pega outra palavra), a rota devolve uma
# categoria ("basic_acronym") que este priority_answer não reconhece em
# nenhum "if route ==" abaixo — a função cai até o fim e devolve None,
# mesmo com uma rota específica (leadership, contact etc.) que bateria
# perfeitamente. _classify_question_base é uma referência fixa à função
# ORIGINAL definida acima, capturada aqui — antes do rebind acontecer —
# para este fallback nunca ser sequestrado pela camada básica.
_classify_question_base = classify_question


def priority_answer(
    question: str,
) -> Optional[str]:

    route = _classify_question_base(
        question
    )

    if route is None:
        return None


    # ------------------------------------------------------------------
    # CARDÁPIO
    # ------------------------------------------------------------------

    if route == "menu":
        return _menu_today()


    # ------------------------------------------------------------------
    # BANCA DE TCC
    # ------------------------------------------------------------------

    if route == "tcc_board":
        return (
            "Segundo a Resolução FCT 01/2012 disponível no portal oficial, "
            "a banca final de TCC II deve observar regras específicas. "
            "Quando há coorientador, sugere-se quatro membros, incluindo "
            "orientador e coorientador; sem coorientador, sugere-se três. "
            "A banca pode ter mais membros, mas não menos que o número "
            "indicado. Também deve existir relação entre a área de atuação "
            "dos avaliadores e o tema do TCC. É permitida a participação "
            "de pós-graduandos e profissionais de reconhecida competência "
            "técnica, mas cada banca deve ter pelo menos dois professores "
            "do quadro efetivo da UFPA. "
            "A defesa de TCC II é avaliada pela banca examinadora e a "
            "resolução também disciplina prazos e procedimentos da defesa. "
            f"Fonte oficial FCT: {FCT_TCC_RESOLUCAO} "
            f"| Instruções da FCT: {FCT_DOCUMENTACAO} "
            f"| Norma geral de Trabalho de Curso da PROEG: {PROEG_TCC_2023}"
        )


    # ------------------------------------------------------------------
    # TCC GERAL
    # ------------------------------------------------------------------

    if route == "tcc":
        return (
            "Para TCC, a FCT mantém instruções institucionais sobre "
            "matrícula, agendamento de defesa e entrega da documentação "
            "após a defesa. A faculdade também disponibiliza a "
            "Resolução FCT 01/2012 sobre TCC. Como existe ainda norma "
            "geral da PROEG sobre Trabalho de Curso, a resposta deve "
            "considerar o assunto específico perguntado e a norma vigente "
            "aplicável. "
            f"Documentação FCT: {FCT_DOCUMENTACAO} "
            f"| Resolução FCT: {FCT_TCC_RESOLUCAO} "
            f"| PROEG: {PROEG_TCC_2023}"
        )


    # ------------------------------------------------------------------
    # ESTÁGIO
    # ------------------------------------------------------------------

    if route == "internship":
        return (
            "A FCT possui uma página oficial específica para estágio. "
            "Nela, a Faculdade direciona para informações e procedimentos "
            "relativos a estágio obrigatório e não obrigatório. "
            "Para responder uma regra pontual — por exemplo, documentação, "
            "integralização, assinatura, carga horária ou início do estágio — "
            "a Minerva deve consultar primeiro essa orientação da FCT e "
            "complementar com a documentação institucional disponível na base. "
            f"Fonte oficial FCT: {FCT_ESTAGIO}"
        )


    # ------------------------------------------------------------------
    # MATRÍCULA
    # ------------------------------------------------------------------

    if route == "enrollment":
        return (
            "A matrícula na UFPA é feita pelo **SIGAA** (Sistema Integrado "
            "de Gestão de Atividades Acadêmicas), o sistema acadêmico "
            "oficial da universidade — acesse pelo portal da UFPA ou "
            f"diretamente em {SIGAA_URL}, com seu login institucional.\n\n"
            "O processo tem duas etapas: você faz a **solicitação** de "
            "matrícula nas turmas desejadas dentro do prazo do calendário "
            "acadêmico; só depois, quando o sistema roda o processamento, "
            "a matrícula é efetivamente confirmada nas turmas, conforme as "
            "regras do Regulamento de Graduação — a solicitação sozinha "
            "não garante a vaga.\n\n"
            "Os prazos de matrícula constam no calendário acadêmico. "
            f"Fonte oficial (prazos): {PROEG_CALENDARIO} "
            "| Fonte institucional (passo a passo no sistema): "
            "Manual SIGAA - UFPA (Discentes), documento da base da FCT/UFPA."
        )


    # ------------------------------------------------------------------
    # TRANCAMENTO DE MATRÍCULA
    # ------------------------------------------------------------------

    if route == "matricula_trancamento":
        return (
            "O trancamento de matrícula é tratado no **Art. 24 do "
            "Regulamento de Graduação da UFPA**. Pontos principais:\n\n"
            "- Você requer o trancamento à Faculdade/Escola, informando o "
            "período letivo e a justificativa do afastamento.\n"
            "- O pedido é apreciado pela Direção da Faculdade e, se "
            "deferido, autorizado junto ao CIAC (Centro de Registro e "
            "Indicadores Acadêmicos).\n"
            "- O período **cumulativo** de trancamento não pode "
            "ultrapassar **2 períodos letivos consecutivos ou 4 "
            "alternados**.\n"
            "- Esse período conta no prazo de integralização do curso "
            "(não é tempo \"de graça\" fora do prazo do curso).\n"
            "- Casos previstos em lei são exceção às regras acima.\n\n"
            f"Fonte oficial: {PROEG_REGULAMENTO}"
        )


    # ------------------------------------------------------------------
    # APROVEITAMENTO DE ESTUDOS
    # ------------------------------------------------------------------

    if route == "aproveitamento_estudos":
        return (
            "O aproveitamento de estudos é tratado nos **Art. 36 e 37 do "
            "Regulamento de Graduação da UFPA**. Pontos principais:\n\n"
            "- A solicitação é analisada pelo Conselho da Faculdade/Escola, "
            "considerando habilidades, competências, conteúdo e carga "
            "horária da atividade pleiteada.\n"
            "- Só são validadas atividades cursadas em instituições "
            "reconhecidas ou autorizadas pelo órgão competente.\n"
            "- É registrado no histórico com a sigla **AE** e **não entra** "
            "no cálculo do coeficiente de rendimento.\n"
            "- Aproveitamento **direto**: quando carga horária e conteúdo "
            "são idênticos, equivalentes ou superiores aos da disciplina "
            "pleiteada.\n"
            "- Aproveitamento **com complementação**: quando o conteúdo "
            "cursado é inferior ao pleiteado em até 30% — a Subunidade "
            "pode exigir avaliação especial ou estudos complementares do "
            "que faltou.\n\n"
            f"Fonte oficial: {PROEG_REGULAMENTO}"
        )


    # ------------------------------------------------------------------
    # GUIA DO CALOURO
    # ------------------------------------------------------------------

    if route == "guia_calouro":
        return (
            "Para quem está começando na FCT, o Centro Acadêmico de "
            "Engenharia da Computação (CAECOMP) mantém o **Guia do "
            "Mochileiro de EngComp** — material feito por alunos para "
            "alunos, cobrindo direitos do aluno, locais importantes do "
            "campus, como se formar e oportunidades acadêmicas.\n\n"
            f"Acesse o guia completo: {GUIA_MOCHILEIRO_CAECOMP}\n"
            f"Página oficial da FCT que indica o guia: {FCT_GUIA_CALOURO}"
        )


    # ------------------------------------------------------------------
    # ATIVIDADES COMPLEMENTARES
    # ------------------------------------------------------------------

    if route == "atividades_complementares":
        return (
            "Atividades complementares têm resolução própria (Resolução "
            "FCT 01/2013) e um passo a passo de integralização "
            "disponibilizado pela FCT. A página oficial não detalha carga "
            "horária/prazos diretamente — o documento de passo a passo "
            "linkado nela é a fonte definitiva.\n\n"
            f"Página oficial: {FCT_ATIVIDADES_COMPLEMENTARES}\n"
            f"Documentação geral da FCT (resoluções e formulários): {FCT_DOCUMENTACAO}"
        )


    # ------------------------------------------------------------------
    # REGULAMENTO DA GRADUAÇÃO
    # ------------------------------------------------------------------

    if route == "graduation_regulation":
        return (
            "O Regulamento do Ensino de Graduação da UFPA reúne princípios "
            "e normas gerais da graduação. O portal da PROEG destaca temas "
            "como estrutura curricular, possibilidades de oferta de curso, "
            "pesquisa e extensão como estratégias de formação e avaliação "
            "para o planejamento acadêmico. Para uma resposta específica, "
            "informe o tema desejado, como matrícula, trancamento, "
            "aproveitamento de estudos ou avaliação. "
            f"Fonte oficial PROEG: {PROEG_REGULAMENTO} "
            f"| Legislação: {PROEG_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # REGIMENTO FCT
    # ------------------------------------------------------------------

    if route == "fct_regiment":
        return (
            "A FCT possui regimento próprio para disciplinar sua "
            "organização institucional. Para questões sobre Conselho da "
            "Faculdade, Direção, estrutura acadêmica ou competências "
            "internas, esse documento deve ser priorizado. "
            f"Documento oficial FCT: {FCT_REGIMENTO} "
            f"| Documentação institucional: {FCT_DOCUMENTACAO}"
        )


    # ------------------------------------------------------------------
    # REGIMENTO GERAL UFPA
    # ------------------------------------------------------------------

    if route == "ufpa_regiment":
        return (
            "O Regimento Geral da UFPA disciplina a organização e o "
            "funcionamento institucional da Universidade. A página oficial "
            "de legislação da UFPA disponibiliza o Regimento Geral e outros "
            "documentos institucionais para consulta. "
            f"Fonte oficial: {UFPA_LEGISLACAO}"
        )


    # ------------------------------------------------------------------
    # DOCENTES
    # ------------------------------------------------------------------

    if route == "faculty":

        faculty = _faculty_list(
            _page_text(
                FCT_DOCENTES
            )
        )

        if faculty:
            return (
                "Segundo a página oficial de Corpo Docente da FCT/UFPA, "
                "os docentes listados são: "
                + "; ".join(faculty)
                + ". "
                + f"Fonte oficial: {FCT_DOCENTES}"
            )

        return (
            "A relação institucional de professores está disponível "
            "na página oficial de Corpo Docente da FCT/UFPA. "
            f"Fonte oficial: {FCT_DOCENTES}"
        )


    # ------------------------------------------------------------------
    # DIREÇÃO
    # ------------------------------------------------------------------

    if route == "leadership":

        text = (
            _page_text(FCT_CONTATO)
            or
            _page_text(FCT_SOBRE)
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

        q = _norm(question)

        if "vice" in q and vice:
            return (
                f"O vice-diretor da FCT/UFPA é {vice}. "
                f"Fonte oficial: {FCT_CONTATO}"
            )

        if director:
            return (
                f"O diretor da FCT/UFPA é {director}. "
                f"Fonte oficial: {FCT_CONTATO}"
            )

        return (
            "A informação atual sobre a direção deve ser consultada "
            "na página oficial de contato da FCT/UFPA. "
            f"Fonte oficial: {FCT_CONTATO}"
        )


    # ------------------------------------------------------------------
    # CURSOS
    # ------------------------------------------------------------------

    if route == "courses":
        return (
            "A FCT/UFPA oferece os cursos de Engenharia da Computação "
            "e Engenharia de Telecomunicações. "
            f"Fonte oficial: {FCT_SOBRE}"
        )


    # ------------------------------------------------------------------
    # CONTATO
    # ------------------------------------------------------------------

    if route == "contact":

        text = _page_text(
            FCT_CONTATO
        )

        phone = _label_value(
            text,
            ["Telefone"],
        )

        email = _label_value(
            text,
            ["E-mail", "Email"],
        )

        # Bug real: na página de contato da FCT, "E-mail" é o rótulo de um
        # ITEM DE MENU (Serviços: Secretaria / E-mail / Sigaa / Contato...),
        # não um par rótulo-valor. _label_value pegava a linha seguinte do
        # menu ("Sigaa") como se fosse o e-mail. Só aceita o valor extraído
        # se realmente parecer um e-mail.
        if email and "@" not in email:
            email = None

        # FCT_CONTATO não expõe endereço estruturado para extrair ao vivo, e
        # o telefone às vezes não está presente na página no formato que
        # _label_value reconhece — usa o telefone/endereço conhecidos
        # (FCT_ENDERECO/FCT_TELEFONE_CONHECIDO) como complemento/fallback.
        values: List[str] = []

        if email:
            values.append(
                f"e-mail {email}"
            )

        values.append(
            f"telefone {phone or FCT_TELEFONE_CONHECIDO}"
        )

        values.append(
            f"localização {FCT_ENDERECO}"
        )

        return (
            "Os dados oficiais de contato/localização da FCT/UFPA são: "
            + "; ".join(values)
            + ". "
            + f"Fonte oficial: {FCT_CONTATO}"
        )

        return (
            "Os dados institucionais de contato estão disponíveis "
            "na página oficial da FCT/UFPA. "
            f"Fonte oficial: {FCT_CONTATO}"
        )


    # ------------------------------------------------------------------
    # CALENDÁRIO
    # ------------------------------------------------------------------

    if route == "calendar":
        return (
            "O calendário acadêmico oficial da UFPA é mantido pela PROEG. "
            "Para obter uma data precisa, informe o evento desejado, como "
            "matrícula, início das aulas, ajuste de matrícula ou término "
            "do período letivo. "
            f"Fonte oficial: {PROEG_CALENDARIO}"
        )


    # ------------------------------------------------------------------
    # DISCENTES
    # ------------------------------------------------------------------

    if route == "student_rules":
        return (
            "As regras aplicáveis aos discentes devem ser verificadas "
            "conforme o assunto. Em termos gerais, a Minerva deve considerar "
            "o Regulamento do Ensino de Graduação da UFPA, o Regimento Geral "
            "da Universidade, o regimento da FCT e eventuais resoluções "
            "específicas da Faculdade. "
            f"PROEG: {PROEG_REGULAMENTO} "
            f"| UFPA: {UFPA_LEGISLACAO} "
            f"| FCT: {FCT_REGIMENTO}"
        )


    # ------------------------------------------------------------------
    # NORMAS FCT
    # ------------------------------------------------------------------

    if route == "fct_rules":
        return (
            "Para regras institucionais da FCT, a Minerva deve priorizar "
            "o Regimento da Faculdade e a seção oficial de Documentação. "
            "Assuntos específicos, como TCC, podem possuir resolução própria. "
            f"Regimento FCT: {FCT_REGIMENTO} "
            f"| Documentação: {FCT_DOCUMENTACAO} "
            f"| TCC: {FCT_TCC_RESOLUCAO}"
        )


    # ------------------------------------------------------------------
    # GUIAS E MANUAIS DA PROEG
    # ------------------------------------------------------------------

    if route == "proeg_manuais":
        return (
            "A PROEG (Pró-Reitoria de Ensino de Graduação) mantém uma página "
            "oficial de Guias e Manuais, voltada principalmente a docentes, "
            "com tutoriais e formulários de apoio às atividades acadêmicas:\n\n"
            f"- **Tutorial de execução de Bolsa Monitoria e LabINFRA**: {PROEG_TUTORIAL_LABINFRA_MONITORIA}\n"
            f"- **SIGAA — Tutorial do portal do docente**: {PROEG_SIGAA_DOCENTE}\n"
            f"- **AVALIA — Formulário Discente (ERE)**: {PROEG_AVALIA_DISCENTE}\n"
            f"- **AVALIA — Formulário Docente (ERE)**: {PROEG_AVALIA_DOCENTE}\n"
            f"- **LabINFRA — Procedimentos para despesas**: {PROEG_LABINFRA_DESPESAS}\n\n"
            f"Fonte oficial (lista completa): {PROEG_GUIAS_MANUAIS}"
        )


    # ------------------------------------------------------------------
    # DOCUMENTAÇÃO
    # ------------------------------------------------------------------

    if route == "documentation":
        return (
            "A FCT mantém uma seção oficial de Documentação com "
            "orientações e materiais institucionais. "
            f"Fonte oficial: {FCT_DOCUMENTACAO}"
        )


    # ------------------------------------------------------------------
    # PLANOS
    # ------------------------------------------------------------------

    if route == "discipline_plans":
        return (
            "A FCT mantém uma página oficial de planos das disciplinas, "
            "incluindo materiais vinculados aos cursos da Faculdade. "
            f"Fonte oficial: {FCT_PLANOS}"
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
            "UFPA significa Universidade Federal do Pará."
        )


    return None


def debug_route(
    question: str,
) -> dict:

    return {
        "question": question,
        "route": classify_question(
            question
        ),
        "answer": priority_answer(
            question
        ),
    }


__all__ = [
    "classify_question",
    "priority_answer",
    "debug_route",
]


# MINERVA_BASIC_FACTS_BEGIN
try:
    from .minerva_basic_facts import (
        basic_answer as _minerva_basic_answer,
        classify_basic_question as _minerva_classify_basic_question,
    )
except (ImportError, ValueError):
    from minerva_basic_facts import (
        basic_answer as _minerva_basic_answer,
        classify_basic_question as _minerva_classify_basic_question,
    )

# MINERVA_DATASET_BEGIN
try:
    from .minerva_dataset import resposta_dataset as _minerva_resposta_dataset
except (ImportError, ValueError):
    from minerva_dataset import resposta_dataset as _minerva_resposta_dataset
# MINERVA_DATASET_END


# Preservar todo o roteamento anterior:
# FCT, ITEC, PPGEE, PROAES, PROEG, RAG etc.
_minerva_router_before_basic_classify = classify_question
_minerva_router_before_basic_answer = priority_answer


def classify_question(question: str):
    """
    Perguntas explicitamente básicas/siglas vêm primeiro.

    Exemplos:
    - O que significa FCT?
    - O que é UFPA?
    - O que significa ITEC?
    - O que é PPGEE?

    Perguntas complexas permanecem no router anterior.
    """

    # Bug real (achado por teste automatizado): esta função substitui o
    # classify_question original no namespace do módulo (late binding — todo
    # chamador, inclusive dentro do router "anterior", passa a resolver para
    # esta versão). O guard contra input não-string existia no original e
    # não tinha sido repetido aqui, então debug_route(question=None) ou
    # qualquer entrada não-string quebrava com TypeError em vez de None.
    if not isinstance(question, str):
        return None

    basic_route = _minerva_classify_basic_question(
        question
    )

    if basic_route is not None:
        return basic_route

    return _minerva_router_before_basic_classify(
        question
    )


def priority_answer(question: str):
    """
    Camada básica antes dos fallbacks genéricos.

    Não intercepta:
    - cursos
    - TCC complexo
    - estágio
    - cardápio
    - professores
    - normas
    - RAG
    """

    basic_result = _minerva_basic_answer(
        question
    )

    if basic_result is not None:
        return basic_result

    resultado_router = _minerva_router_before_basic_answer(
        question
    )

    if resultado_router is not None:
        return resultado_router

    # Último recurso, prioridade baixa: dataset de perguntas cadastradas
    # manualmente (minerva_dataset.json). Só entra quando nada acima já
    # respondeu — não compete com nenhuma rota fixa existente.
    return _minerva_resposta_dataset(
        question
    )


try:
    if isinstance(__all__, list):

        for _basic_export in (
            "classify_question",
            "priority_answer",
        ):
            if _basic_export not in __all__:
                __all__.append(
                    _basic_export
                )

except NameError:
    pass

# MINERVA_BASIC_FACTS_END

