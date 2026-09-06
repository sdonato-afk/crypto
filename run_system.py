# run_system.py - Servidor HTTP Protegido + Bot Engine Integrado + Self Keep-Alive Anti-Sleep
import http.server
import socketserver
import threading
import urllib.request
import urllib.parse
import webbrowser
import json
import time
import os
import sys
import base64
from binance_bot_engine import BinanceBotEngine, log_message

PORT = int(os.environ.get("PORT", 5000))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://crypto-3d7e.onrender.com")

# Credenciales de protección del Dashboard (configurables vía variables de entorno)
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.environ.get("DASHBOARD_PASS", "cripto2026")
EXPECTED_AUTH = "Basic " + base64.b64encode(f"{DASHBOARD_USER}:{DASHBOARD_PASS}".encode("utf-8")).decode("utf-8")

# Archivo de cierres manuales pendientes
PENDING_CLOSES_FILE = "pending_closes.json"

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP habituales

    def check_auth(self):
        auth_header = self.headers.get("Authorization")
        if auth_header == EXPECTED_AUTH:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Bot Cripto Dashboard Acceso Protegido"')
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>401 Acceso No Autorizado</h1>")
        return False

    def do_GET(self):
        if not self.check_auth():
            return

        state_file = os.environ.get("STATE_FILE_NAME", "cripto_bot_estado.json")
        if self.path == "/cripto_bot_estado.json" and state_file != "cripto_bot_estado.json":
            self.path = "/" + state_file

        super().do_GET()

    def do_HEAD(self):
        if not self.check_auth():
            return
        super().do_HEAD()

    def do_POST(self):
        """Endpoint de control remoto para el bot."""
        if not self.check_auth():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # --- POST /api/force_close  (body: {"ticker": "USD1"}) ---
        if path == "/api/force_close":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                payload = json.loads(body.decode("utf-8"))
                ticker = payload.get("ticker", "").upper().strip()

                if not ticker:
                    raise ValueError("ticker vacío")

                # Leer lista actual de cierres pendientes
                pending = []
                if os.path.exists(PENDING_CLOSES_FILE):
                    with open(PENDING_CLOSES_FILE, "r") as f:
                        pending = json.load(f)

                if ticker not in pending:
                    pending.append(ticker)

                with open(PENDING_CLOSES_FILE, "w") as f:
                    json.dump(pending, f)

                log_message("MANUAL_CLOSE", f"Cierre manual solicitado para [{ticker}]. Se ejecutará en el próximo ciclo.")
                self._json_response(200, {"ok": True, "message": f"Cierre de {ticker} encolado. Se ejecutará en ~10 segundos."})

            except Exception as e:
                self._json_response(400, {"ok": False, "error": str(e)})
        else:
            self._json_response(404, {"ok": False, "error": "Endpoint no encontrado"})

    def _json_response(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_http_server():
    Handler = QuietHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        log_message("INFO", f"Servidor Web Protegido activo en el puerto {PORT} (Usuario: {DASHBOARD_USER})")
        httpd.serve_forever()

def keep_alive_loop():
    """Hilo de Keep-Alive: Pinea el servidor en Render cada 4 minutos para evitar que se ponga a dormir"""
    log_message("INFO", "Hilo Keep-Alive Anti-Sleep iniciado.")
    time.sleep(30)
    while True:
        try:
            url = f"{RENDER_EXTERNAL_URL}/cripto_bot_estado.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'KeepAliveBot/1.0'})
            req.add_header('Authorization', EXPECTED_AUTH)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    log_message("KEEP_ALIVE", "Ping Anti-Sleep exitoso. Servidor despierto en la nube.")
        except Exception as e:
            log_message("KEEP_ALIVE_WARN", f"Ping Anti-Sleep intentado ({e})")
        time.sleep(240)

def main():
    log_message("INFO", f"=== INICIANDO BOT CRIPTO CON MANTENIMIENTO 24/7 Y DASHBOARD PROTEGIDO (PUERTO {PORT}) ===")
    log_message("INFO", f"Credenciales Dashboard -> Usuario: '{DASHBOARD_USER}' | Password: '****'")

    # 1. Iniciar Servidor HTTP local/cloud
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    # 2. Iniciar Hilo Anti-Sleep para mantener a Render despierto 24/7
    if "RENDER" in os.environ:
        keep_thread = threading.Thread(target=keep_alive_loop, daemon=True)
        keep_thread.start()
    else:
        if not os.environ.get("NO_BROWSER"):
            try:
                webbrowser.open(f"http://localhost:{PORT}/dashboard_cripto.html")
            except Exception:
                pass

    # 3. Correr loop continuo del Motor de Trading
    engine = BinanceBotEngine()
    consecutive_errors = 0
    while True:
        try:
            engine.run_cycle()
            consecutive_errors = 0
            time.sleep(10)
        except KeyboardInterrupt:
            log_message("WARN", "Bot Cripto detenido por el usuario.")
            break
        except Exception as e:
            consecutive_errors += 1
            wait = min(60 * consecutive_errors, 300)
            log_message("ERROR", f"Error crítico #{consecutive_errors}: {e}. Esperando {wait}s...")
            time.sleep(wait)

if __name__ == "__main__":
    main()
