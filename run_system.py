# run_system.py - Servidor HTTP + Bot Engine Integrado (Compatible con Render.com & Local)
import http.server
import socketserver
import threading
import webbrowser
import time
import os
import sys
from binance_bot_engine import BinanceBotEngine, log_message

# Render asigna dinámicamente la variable de entorno PORT (ej. 10000)
PORT = int(os.environ.get("PORT", 5000))

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silenciar logs de peticiones HTTP en la consola

def run_http_server():
    Handler = QuietHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        log_message("INFO", f"Servidor Web activo en el puerto {PORT}")
        httpd.serve_forever()

def main():
    log_message("INFO", f"=== INICIANDO BOT CRIPTO Y SERVIDOR WEB (PUERTO {PORT}) ===")
    
    # 1. Iniciar Servidor HTTP local en hilo secundario (Daemon)
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    # 2. Si es ejecución local (no en Render), abrir navegador automáticamente
    if "RENDER" not in os.environ:
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
