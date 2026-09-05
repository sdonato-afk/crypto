# run_system.py - Servidor HTTP Protegido + Bot Engine Integrado + Self Keep-Alive Anti-Sleep
import http.server
import socketserver
import threading
import urllib.request
import webbrowser
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

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silenciar logs HTTP habituales

    def check_auth(self):
        auth_header = self.headers.get("Authorization")
        if auth_header == EXPECTED_AUTH:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Bot Cripto Dashboard Acceso Protegido"')
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>401 Acceso No Autorizado</h1><p>Credenciales requeridas para acceder al Dashboard del Bot Cripto.</p>")
        return False

    def do_GET(self):
        if not self.check_auth():
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.check_auth():
            return
        super().do_HEAD()

def run_http_server():
    Handler = QuietHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        log_message("INFO", f"Servidor Web Protegido activo en el puerto {PORT} (Usuario: {DASHBOARD_USER})")
        httpd.serve_forever()

def keep_alive_loop():
    """Hilo de Keep-Alive: Pinea el servidor en Render cada 4 minutos para evitar que se ponga a dormir"""
    log_message("INFO", "Hilo Keep-Alive Anti-Sleep iniciado.")
    time.sleep(30) # Esperar arranque del servidor
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
        time.sleep(240) # Pinear cada 4 minutos (240 segundos)

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
        try:
            webbrowser.open(f"http://localhost:{PORT}/dashboard_cripto.html")
        except Exception:
            pass

    # 3. Correr loop continuo del Motor de Trading
    engine = BinanceBotEngine()
    try:
        while True:
            engine.run_cycle()
            time.sleep(10)
    except KeyboardInterrupt:
        log_message("WARN", "Bot Cripto detenido.")

if __name__ == "__main__":
    main()

