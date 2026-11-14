"""Formulário de avaliação da Minerva para alunos da FCT/UFPA.

Instrumento em três blocos:

1. PERFIL — curso, semestre e familiaridade com assistentes de IA
   (caracterização dos participantes exigida na avaliação experimental
   da dissertação).
2. SUS (System Usability Scale, Brooke 1996) — 10 itens Likert 1–5,
   instrumento validado e comparável com a literatura (média de
   referência: 68 pontos). Itens adaptados ao contexto da Minerva.
3. ESPECÍFICAS DO RAG — percepção de correção, citação de fonte,
   latência e rotas rápidas + 3 perguntas abertas.

As funções de pontuação são puras (sem Streamlit/banco) para permitir
teste unitário; a renderização importa Streamlit apenas dentro da
função, seguindo o padrão dos demais módulos minerva_*.
"""
from __future__ import annotations

import json

ESCALA_LIKERT = [
    "1 — Discordo totalmente",
    "2 — Discordo",
    "3 — Neutro",
    "4 — Concordo",
    "5 — Concordo totalmente",
]

CURSOS_FCT = [
    "Ciência da Computação",
    "Engenharia da Computação",
    "Engenharia de Telecomunicações",
    "Outro curso da UFPA",
    "Não sou aluno(a) da UFPA",
]

FREQUENCIA_IA = [
    "Nunca usei assistentes de IA",
    "Uso raramente (menos de 1x por semana)",
    "Uso toda semana",
    "Uso todo dia",
]

# Os 10 itens do SUS na ordem canônica: ímpares (1º, 3º...) são afirmações
# positivas, pares são negativas — a alternância é parte do instrumento
# (reduz respostas automáticas) e o cálculo do score depende dela.
ITENS_SUS = [
    "Eu usaria a Minerva com frequência para tirar dúvidas acadêmicas.",
    "Achei a Minerva desnecessariamente complexa.",
    "Achei a Minerva fácil de usar.",
    "Eu precisaria de ajuda de outra pessoa para conseguir usar a Minerva.",
    "As funções da Minerva (chat, categorias, downloads, conversas) estão bem integradas.",
    "Achei que a Minerva tem muitas inconsistências.",
    "Imagino que a maioria dos alunos aprenderia a usar a Minerva rapidamente.",
    "Achei a Minerva confusa de usar.",
    "Me senti confiante usando a Minerva.",
    "Precisei aprender muitas coisas antes de conseguir usar a Minerva.",
]

ITENS_RAG = [
    "As respostas estavam corretas em relação aos documentos oficiais da FCT/UFPA.",
    "A Minerva deixou claro de qual documento/fonte veio a informação.",
    "O tempo de espera pelas respostas foi aceitável.",
    "Perguntas rápidas (calendário, cardápio do RU, contatos) foram respondidas de imediato.",
]


def calcular_sus(respostas: list[int]) -> float:
    """Pontuação SUS oficial, de 0 a 100.

    Itens ímpares (índice par na lista): contribuição = resposta - 1.
    Itens pares (índice ímpar): contribuição = 5 - resposta.
    Soma das contribuições (0–40) multiplicada por 2,5.
    """
    if len(respostas) != len(ITENS_SUS):
        raise ValueError(f"SUS exige {len(ITENS_SUS)} respostas, veio {len(respostas)}")

    if any(not isinstance(r, int) or r < 1 or r > 5 for r in respostas):
        raise ValueError("Respostas SUS devem ser inteiros entre 1 e 5")

    contribuicoes = [
        (r - 1) if i % 2 == 0 else (5 - r)
        for i, r in enumerate(respostas)
    ]

    return sum(contribuicoes) * 2.5


def montar_registro(
    curso: str,
    semestre: str,
    frequencia_ia: str,
    respostas_sus: list[int],
    respostas_rag: list[int],
    ponto_forte: str,
    ponto_fraco: str,
    pergunta_errada: str,
) -> dict:
    """Consolida o formulário num dicionário pronto para persistir (JSONB)."""
    return {
        "curso": curso,
        "semestre": semestre,
        "frequencia_ia": frequencia_ia,
        "sus_respostas": respostas_sus,
        "sus_score": calcular_sus(respostas_sus),
        "rag_itens": dict(zip(ITENS_RAG, respostas_rag, strict=True)),
        "ponto_forte": ponto_forte.strip(),
        "ponto_fraco": ponto_fraco.strip(),
        "pergunta_errada": pergunta_errada.strip(),
    }


def _indice_likert(valor: str) -> int:
    """'3 — Neutro' -> 3."""
    return int(valor.split(" ", 1)[0])


def render_formulario_avaliacao(salvar_func, session_id: str) -> None:
    """Desenha o formulário no Streamlit e persiste via salvar_func.

    salvar_func(session_id, registro_dict) é injetada por main.py (padrão
    já usado com llm_func em responder_minerva) — este módulo não conhece
    o banco.
    """
    import streamlit as st

    st.markdown("### 📝 Avaliação da Minerva")
    st.caption(
        "Pesquisa acadêmica com alunos da FCT/UFPA — leva menos de 5 minutos. "
        "As respostas são anônimas e usadas apenas para melhorar o sistema."
    )

    if st.session_state.get("avaliacao_enviada"):
        st.success(
            "Avaliação registrada — obrigado por contribuir! "
            "Você pode voltar ao chat pela barra lateral."
        )
        return

    with st.form("form_avaliacao_minerva"):
        st.markdown("#### Sobre você")
        curso = st.selectbox("Curso", CURSOS_FCT)
        semestre = st.selectbox(
            "Semestre em curso",
            [str(n) for n in range(1, 11)] + ["Acima do 10º", "Não se aplica"],
        )
        frequencia_ia = st.radio(
            "Com que frequência você usa assistentes de IA (ChatGPT, Gemini...)?",
            FREQUENCIA_IA,
        )

        st.divider()
        st.markdown("#### Usabilidade (SUS)")
        st.caption("Marque o quanto concorda com cada afirmação.")
        respostas_sus = [
            _indice_likert(
                st.radio(item, ESCALA_LIKERT, index=2, key=f"sus_{i}", horizontal=True)
            )
            for i, item in enumerate(ITENS_SUS)
        ]

        st.divider()
        st.markdown("#### Qualidade das respostas")
        respostas_rag = [
            _indice_likert(
                st.radio(item, ESCALA_LIKERT, index=2, key=f"rag_{i}", horizontal=True)
            )
            for i, item in enumerate(ITENS_RAG)
        ]

        st.divider()
        st.markdown("#### Na sua opinião")
        ponto_forte = st.text_area("O que você mais gostou na Minerva?")
        ponto_fraco = st.text_area("O que deveria melhorar?")
        pergunta_errada = st.text_area(
            "Alguma pergunta que a Minerva errou ou não soube responder? Qual?"
        )

        enviado = st.form_submit_button("Enviar avaliação", type="primary")

    if enviado:
        registro = montar_registro(
            curso=curso,
            semestre=semestre,
            frequencia_ia=frequencia_ia,
            respostas_sus=respostas_sus,
            respostas_rag=respostas_rag,
            ponto_forte=ponto_forte,
            ponto_fraco=ponto_fraco,
            pergunta_errada=pergunta_errada,
        )
        salvar_func(session_id, registro)
        st.session_state.avaliacao_enviada = True
        st.rerun()


def registro_para_json(registro: dict) -> str:
    """Serialização estável para a coluna JSONB (ensure_ascii preserva acentos)."""
    return json.dumps(registro, ensure_ascii=False)
