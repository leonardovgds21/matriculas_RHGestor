"""Servidor do site simulado: devolve o index.html para todas as rotas (o
index.html monta a tela de cada endereço)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGINA = (Path(__file__).parent / "index.html").read_bytes()
# Imita a verificação de segurança (Cloudflare) antes do login: some sozinha
# depois de 2 s num navegador visível; no invisível fica parada.
DESAFIO = ("<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>"
           "<h1>sistema.rhgestor.com.br</h1><p>Verify you are human by completing the action below.</p>"
           "<script>if (!/HeadlessChrome/.test(navigator.userAgent)) setTimeout(() => {"
           "document.cookie = 'cf_ok=1; path=/'; location.reload(); }, 2000);</script></body></html>").encode()
com_desafio = False


class Pagina(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        corpo = PAGINA
        if com_desafio and self.path.lower().startswith("/login") and "cf_ok=1" not in (self.headers.get("Cookie") or ""):
            corpo = DESAFIO
        self.send_response(403 if corpo is DESAFIO else 200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass


def iniciar(porta: int = 0) -> tuple[ThreadingHTTPServer, str]:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Pagina)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


if __name__ == "__main__":
    s, url = iniciar(8766)
    print(f"Site simulado em {url}/login (login gestor, senha teste). Ctrl+C para sair.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.shutdown()
