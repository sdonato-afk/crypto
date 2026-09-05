# telegram_notifier.py - Módulo de Notificaciones en Tiempo Real a Telegram
import json
import urllib.request
import os

TELEGRAM_CONFIG_FILE = "telegram_config.json"

class TelegramNotifier:
    def __init__(self):
        self.bot_token = ""
        self.chat_id = ""
        self.enabled = False
        self.load_config()

    def load_config(self):
        # 1. Intentar cargar desde variables de entorno (Ideal para Render.com / Cloud)
        env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        env_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

        if env_token and env_chat:
            self.bot_token = env_token
            self.chat_id = env_chat
            self.enabled = True
            return

        # 2. Si no hay variables de entorno, cargar desde archivo local json
        if os.path.exists(TELEGRAM_CONFIG_FILE):
            try:
                with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.bot_token = cfg.get("bot_token", "").strip()
                    self.chat_id = str(cfg.get("chat_id", "")).strip()
                    if self.bot_token and self.chat_id:
                        self.enabled = True
            except Exception:
                self.enabled = False

    def send_message(self, text):
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"[TELEGRAM ERROR] No se pudo enviar mensaje: {e}")
            return False

    def notify_open_slot(self, slot):
        msg = (
            f"🟢 <b>NUEVA POSICIÓN OCO ABIERTA (Paper Trading)</b>\n\n"
            f"🪙 <b>Activo:</b> #{slot['ticker']} ({slot['name']})\n"
            f"💵 <b>Precio Entrada:</b> ${slot['entry_price']}\n"
            f"📊 <b>Score Absorción:</b> {slot['score']} / 100\n"
            f"🎯 <b>Take Profit (OCO):</b> +{slot.get('take_profit_pct', 9.0)}%\n"
            f"🛑 <b>Stop Loss (OCO):</b> {slot.get('stop_loss_pct', -4.0)}%\n"
            f"💰 <b>Capital Asignado:</b> ${slot.get('allocated_capital_usd', 100.0):.2f} USDT\n\n"
            f"<i>Escaneado desde Binance API en vivo.</i>"
        )
        self.send_message(msg)

    def notify_close_slot(self, slot, reason, net_pnl_pct, pnl_usd, total_equity):
        tag = "🎯 <b>TRADE GANADOR (WIN)</b>" if net_pnl_pct > 0 else "🛑 <b>STOP LOSS EJECUTADO (LOSS)</b>"
        msg = (
            f"{tag}\n\n"
            f"🪙 <b>Activo:</b> #{slot['ticker']}\n"
            f"📉 <b>Entrada:</b> ${slot['entry_price']} | 📈 <b>Salida:</b> ${slot['current_price']}\n"
            f"📊 <b>Resultado Neto:</b> {net_pnl_pct:+.2f}% (${pnl_usd:+.2f} USD)\n"
            f"📝 <b>Motivo Cierre:</b> {reason}\n"
            f"💼 <b>Patrimonio Actual:</b> ${total_equity:.2f} USDT\n\n"
            f"<i>Descontada comisión Binance (0.024% con descuento BNB + Maker + Kickback).</i>"
        )
        self.send_message(msg)

    def notify_btc_guard(self, reason):
        msg = (
            f"🚨 <b>ALERTA DE FRENO MACRO (BTC GUARD)</b>\n\n"
            f"{reason}\n\n"
            f"<i>El bot ha bloqueado la apertura de nuevos slots para proteger el capital.</i>"
        )
        self.send_message(msg)
