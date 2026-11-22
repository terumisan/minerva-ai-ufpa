from scripts import agente_ampliacao as ag

TRECHO = {"id": 7, "conteudo": "Art. 12. O discente poderá solicitar o trancamento da matrícula em até 30 dias após o início do período letivo, uma única vez."}
ENTRADAS = [{"id": "MINERVA_0001", "pergunta": "Até quando posso trancar a matrícula?", "variacoes": [], "ativo": True}]


def juiz_ok(*_a, **_k):
    return '{"sustentada": true, "responde": true, "motivo": "ok"}'


def test_citacao_literal_e_numeros():
    assert ag.citacao_no_trecho("poderá solicitar o trancamento da matrícula", TRECHO["conteudo"])
    assert not ag.citacao_no_trecho("pode trancar sempre que quiser no semestre", TRECHO["conteudo"])
    assert ag.numeros_sustentados("Até 45 dias (Art. 12).", TRECHO["conteudo"]) == ["45"]


def test_reprova_numero_inventado():
    c = {"pergunta": "Quantas vezes tranco o curso?", "resposta": "Até 45 dias, Art. 12.",
         "citacao": "poderá solicitar o trancamento da matrícula em até 30 dias"}
    st, mot, _, _ = ag.verificar(c, TRECHO, ENTRADAS, True, juiz_ok)
    assert st == "REPROVADO" and "45" in mot[0]


def test_parecida_vira_variacao_e_nova_passa():
    c = {"pergunta": "Até quando posso trancar a matrícula na faculdade?", "resposta": "Até 30 dias (Art. 12).",
         "citacao": "solicitar o trancamento da matrícula em até 30 dias"}
    assert ag.verificar(c, TRECHO, ENTRADAS, True, juiz_ok)[0] == "VARIACAO"
    c2 = dict(c, pergunta="Quantas vezes posso pedir trancamento?", resposta="Uma única vez (Art. 12).")
    assert ag.verificar(c2, TRECHO, ENTRADAS, True, juiz_ok)[0] == "NOVA"


def test_juiz_reprova_e_json_sujo():
    c = {"pergunta": "x trancamento?", "resposta": "Art. 12.", "citacao": "solicitar o trancamento da matrícula em até 30 dias"}
    ruim = lambda *_a, **_k: '```json\n{"sustentada": false, "responde": true, "motivo": "extrapola"}\n```'
    st, mot, _, _ = ag.verificar(c, TRECHO, ENTRADAS, True, ruim)
    assert st == "REPROVADO" and "extrapola" in mot[0]
    assert ag.extrair_json('Claro! [{"a": 1}] fim') == [{"a": 1}]


def test_auditoria_acha_escopo_copiado_de_outra_entrada():
    # Caso real de 18/11: o escopo da 0239 era cópia do da 0218 (corrigido).
    esc = ("Graduação da UFPA: exercício domiciliar para infecções, traumatismos, "
           "doenças raras e condições temporárias de saúde comprovadas por atestado.")
    def entrada(i, pergunta, resposta):
        return {"id": i, "pergunta": pergunta, "variacoes": [], "resposta_literal": resposta,
                "ativo": True, "contexto_documental": {"escopo": esc}}
    entradas = [entrada("A", "Quem tem direito a exercício domiciliar?",
                        "Discentes com infecções, traumatismos ou doenças raras, com atestado."),
                entrada("B", "Quem resolve casos omissos do regulamento?", "O CONSEPE.")]
    entradas += [{"id": f"X{i}", "pergunta": f"pergunta {i}", "variacoes": [], "ativo": True,
                  "resposta_literal": "r", "contexto_documental": {"escopo": f"escopo generico {i}"}}
                 for i in range(60)]
    achados = ag.escopos_suspeitos(entradas)
    assert "B" in achados and "A" not in achados
