from urllib.error import URLError
from urllib.request import Request

import pytest

import web_segura as web


@pytest.mark.parametrize("url", [
    "https://ufpa.br.exemplo.com/", "http://fct.ufpa.br/", "https://127.0.0.1/",
    "https://usuario:senha@fct.ufpa.br/", "https://fct.ufpa.br:8443/",
])
def test_host_semelhante_http_e_credenciais_bloqueados(url):
    with pytest.raises(URLError):
        web.validar_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"])
def test_destino_privado_bloqueado_antes_da_conexao(monkeypatch, ip):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (ip, 443))])
    with pytest.raises(URLError):
        web.resolver_publico("fct.ufpa.br")


def test_redirecionamento_externo_bloqueado_antes_de_abrir_destino():
    handler = web.RedirecionamentoOficial()
    with pytest.raises(URLError):
        handler.redirect_request(Request("https://fct.ufpa.br/"), None, 302, "", {}, "https://externo.com/")
    req = handler.redirect_request(Request("https://fct.ufpa.br/"), None, 302, "", {}, "https://ufpa.br/")
    assert req.full_url == "https://ufpa.br/"


def test_conexao_usa_ip_validado_e_tls_com_hostname(monkeypatch):
    ips = []
    tls = []
    sock = object()
    monkeypatch.setattr(web, "resolver_publico", lambda h: "8.8.8.8")
    monkeypatch.setattr(web.socket, "create_connection", lambda destino, *a: ips.append(destino) or sock)
    class Context:
        verify_mode = 2
        check_hostname = True
        def wrap_socket(self, socket, server_hostname):
            assert socket is sock
            tls.append(server_hostname)
            return object()
    def do_open(cls, req, **kwargs):
        c = cls("fct.ufpa.br", context=Context())
        c.connect()
        return "ok"
    handler = web.HTTPSOficial()
    monkeypatch.setattr(handler, "do_open", do_open)
    assert handler.https_open(Request("https://fct.ufpa.br/")) == "ok"
    assert ips == [("8.8.8.8", 443)] and tls == ["fct.ufpa.br"]
