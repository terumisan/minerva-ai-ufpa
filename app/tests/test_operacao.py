import pytest

from operacao import inicializar_identidade, capacidade, validar_pergunta


def test_url_nao_autoriza_historico_e_cada_sessao_tem_identidade():
    a, b = {}, {}
    url = {"sid": "identidade_da_vitima", "cid": "conversa_da_vitima"}
    inicializar_identidade(a, url)
    inicializar_identidade(b, {"sid": a["session_id"]})
    assert "sid" not in url
    assert a["session_id"] != b["session_id"]
    sid = a["session_id"]
    inicializar_identidade(a, {"sid": "outro"})
    assert a["session_id"] == sid


def test_migracao_de_sessao_antiga_nao_reutiliza_identidade_da_url():
    estado = {"session_id": "antigo", "messages": ["privado"], "conversa_id": "cid"}
    inicializar_identidade(estado, {})
    assert estado["session_id"] != "antigo"
    assert "messages" not in estado and "conversa_id" not in estado


def test_sobrecarga_nao_enfileira_e_excecao_libera_vaga():
    with pytest.raises(RuntimeError), capacidade({}, agora=10) as erro:
        assert erro is None
        with capacidade({}, agora=10) as ocupado:
            assert "outra consulta" in ocupado
        raise RuntimeError("Falha de rede")
    estado = {}
    with capacidade(estado, agora=15) as erro:
        assert erro is None
    with capacidade(estado, agora=16) as erro:
        assert "Aguarde" in erro
    with capacidade(estado, agora=19) as erro:
        assert erro is None


@pytest.mark.parametrize("entrada", [None, "", "  ", "a" * 4001])
def test_entrada_invalida(entrada):
    assert validar_pergunta(entrada)


def test_entrada_no_limite():
    assert validar_pergunta("a" * 4000) is None
