"""Servidor do site simulado: devolve o index.html para todas as rotas (o
index.html monta a tela de cada endereço)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGINA = (Path(__file__).parent / "index.html").read_bytes()


class Pagina(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGINA)))
        self.end_headers()
        self.wfile.write(PAGINA)

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
