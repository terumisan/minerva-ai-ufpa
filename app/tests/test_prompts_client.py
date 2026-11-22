from types import SimpleNamespace

import prompts


def test_erro_http_fecha_resposta_e_nao_registra_conteudo(monkeypatch, caplog):
    response = SimpleNamespace(status_code=503, text="CONTEUDO_PRIVADO", closed=False)
    def close():
        response.closed = True
    response.close = close
    def post(url, **kwargs):
        assert kwargs["timeout"] == (5, 180)
        return response
    monkeypatch.setattr(prompts, "http_session", SimpleNamespace(post=post))
    assert "Não localizei" in prompts.consultar_modelo_local("PERGUNTA_PRIVADA")
    assert response.closed
    assert "CONTEUDO_PRIVADO" not in caplog.text and "PERGUNTA_PRIVADA" not in caplog.text


def test_barreira_institucional_nao_registra_texto(caplog):
    prompts.validar_resposta_institucional("Texto PRIVADO sobre a UFPE")
    assert "PRIVADO" not in caplog.text
