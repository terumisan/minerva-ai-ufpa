"""HTTP para fontes oficiais, com validação em cada salto e IP fixado por conexão."""
import http.client
import ipaddress
import socket
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, build_opener


def validar_url(url):
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        if (p.scheme != "https" or p.username or p.password or p.port not in (None, 443)
                or not (host == "ufpa.br" or host.endswith(".ufpa.br"))):
            raise ValueError("Origem não permitida")
        return host
    except ValueError as exc:
        raise URLError("URL oficial HTTPS inválida") from exc


def resolver_publico(host):
    enderecos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = [r[4][0] for r in enderecos]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise URLError("Destino privado ou reservado bloqueado")
    return ips[0]


class RedirecionamentoOficial(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validar_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HTTPSOficial(HTTPSHandler):
    def https_open(self, req):
        host = validar_url(req.full_url)
        ip = resolver_publico(host)

        class ConexaoFixada(http.client.HTTPSConnection):
            def connect(self):
                # O mesmo IP validado é usado na conexão; TLS ainda verifica
                # o nome oficial. Não há uma segunda resolução pelo urllib.
                sock = socket.create_connection((ip, 443), self.timeout, self.source_address)
                try:
                    self.sock = self._context.wrap_socket(sock, server_hostname=host)
                except BaseException:
                    sock.close()
                    raise

        return self.do_open(ConexaoFixada, req, context=self._context)


def abrir_url(request, timeout=10):
    validar_url(request.full_url)
    # Proxies do ambiente não podem desviar a conexão validada.
    opener = build_opener(ProxyHandler({}), HTTPSOficial(), RedirecionamentoOficial())
    return opener.open(request, timeout=timeout)
