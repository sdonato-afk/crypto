# run_system.py - Servidor HTTP + Bot Engine Integrado
import http.server
import socketserver
import threading
import webbrowser
import time
import sys
from binance_bot_engine import BinanceBotEngine, log_message

PORT = 5000

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silenciar logs HTTP de la consola

def run_http_server():
    Handler = QuietHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

def main():
    log_message("INFO", "=== INICIANDO SISTEMA CRIPTO CON SERVIDOR WEB LOCAL EN PORT 5000 ===")
    
    # 1. Iniciar Servidor HTTP local en hilo separado
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()
    log_message("INFO", f"Servidor Web activo en http://localhost:{PORT}/dashboard_cripto.html")

    # 2. Abrir navegador automáticamente
    webbrowser.open(f"http://localhost:{PORT}/dashboard_cripto.html")

    # 3. Correr loop del Bot Engine
    engine = BinanceBotEngine()
    try:
        while True:
            engine.run_cycle()
            time.sleep(10)
    except KeyboardInterrupt:
        log_message("WARN", "Bot Cripto detenido.")

if __name__ == "__main__":
    main()
