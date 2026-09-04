# binance_bot_engine.py - Motor de Trading Multi-Posición (10 Slots Simultáneos)
# Arquitectura: Paper Trading en Vivo / Órdenes OCO Nativas / Trailing Escalonado / Reinversión 70-20-10

import time
import json
import os
from datetime import datetime
from crypto_analyzer import CryptoAnalyzer
from telegram_notifier import TelegramNotifier

import sys

# Forzar salida en UTF-8 para consola de Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

STATE_FILE = "cripto_bot_estado.json"
TOP_20_FILE = "top_20_criptos.json"
LOG_FILE = "cripto_bot_ejecucion.log"

MAX_SLOTS = 10
TAKE_PROFIT_PCT = 6.0
STOP_LOSS_PCT = 2.0
TRAILING_STAGE_1 = 3.0  # Mueve SL a Breakeven +0.2% (cubre comisiones de Binance)
TRAILING_STAGE_2 = 4.5  # Mueve SL a +2.5% (Asegura ganancia)
BINANCE_FEE_PCT = 0.075 # Comisión Taker/Maker en Binance usando BNB discount

INITIAL_CAPITAL_USD = 1000.0 # $1,000 USDT de Capital de Prueba Virtual
CAPITAL_PER_SLOT_USD = 100.0  # $100 USDT por slot (10 slots)

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_message(tag, msg):
    formatted = f"[{timestamp()}] [{tag}] {msg}"
    try:
        print(formatted)
    except Exception:
        print(formatted.encode('ascii', 'ignore').decode('ascii'))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

class BinanceBotEngine:
    def __init__(self):
        self.analyzer = CryptoAnalyzer()
        self.telegram = TelegramNotifier()
        self.active_slots = []
        self.trade_history = []
        self.top_20_list = self.load_top_20()
        self.total_wins = 0
        self.total_losses = 0
        
        # Capital Inicial $1,000 USD (Operativo 100%)
        self.operating_capital_usd = 1000.0
        self.reinvested_70_usd = 0.0      # 70% Acumulado de ganancias reinvertidas
        self.drawdown_buffer_usd = 0.0    # 20% Cojín de reserva acumulado
        self.profit_vault_usd = 0.0       # 10% Bóveda de utilidades cosechadas
        self.net_pnl_usd = 0.0

        self.btc_guard_status = {"status": "NORMAL", "reason": "Iniciando bot", "drop_pct": 0.0}
        self.load_state()

    def load_top_20(self):
        if os.path.exists(TOP_20_FILE):
            try:
                with open(TOP_20_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def load_state(self):
        data = None
        
        # 1. Si existe archivo de estado local, cargarlo
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

        # 2. Si es Render y no hay data local o está vacía, intentar recuperar desde GitHub Raw
        if not data and "RENDER" in os.environ:
            try:
                raw_url = "https://raw.githubusercontent.com/sdonato-afk/crypto/main/cripto_bot_estado.json"
                req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    log_message("INFO", "Estado del Bot Cripto recuperado desde GitHub Cloud con éxito.")
            except Exception as e:
                log_message("WARN", f"No se pudo cargar estado remoto desde GitHub ({e})")

        if data:
            self.active_slots = data.get("active_slots", [])
            self.trade_history = data.get("trade_history", [])
            self.net_pnl_usd = data.get("net_pnl_usd", 0.0)
            self.operating_capital_usd = data.get("operating_capital_usd", 1000.0)
            
            # Recalcular Wins y Losses dinámicamente desde el historial real de trades
            self.total_wins = sum(1 for t in self.trade_history if t.get("result") == "WIN")
            self.total_losses = sum(1 for t in self.trade_history if t.get("result") == "LOSS")

            cap_model = data.get("capitalModel", {})
            self.reinvested_70_usd = cap_model.get("compounded_70", 0.0)
            self.drawdown_buffer_usd = cap_model.get("buffer_20", 0.0)
            self.profit_vault_usd = cap_model.get("vault_10", 0.0)
            log_message("INFO", f"Estado cargado: {self.total_wins} Wins / {self.total_losses} Losses.")
            return

        self.active_slots = []

    def save_state(self):
        # Garantizar sincronización exacta de victorias y derrotas desde el historial
        self.total_wins = sum(1 for t in self.trade_history if t.get("result") == "WIN")
        self.total_losses = sum(1 for t in self.trade_history if t.get("result") == "LOSS")

        total_trades = self.total_wins + self.total_losses
        win_rate = (self.total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
        
        # P&L Flotante (Ganancia/Pérdida no realizada de posiciones abiertas)
        floating_pnl_usd = sum(slot.get("pnl_usd", 0.0) for slot in self.active_slots)
        
        # Patrimonio Mark-to-Market en Tiempo Real (Realizado + Flotante)
        total_equity = self.operating_capital_usd + self.drawdown_buffer_usd + self.profit_vault_usd + floating_pnl_usd
        total_net_pnl = self.net_pnl_usd + floating_pnl_usd

        state = {
            "botStatus": "PAPER_TRADING_OCO_ACTIVO",
            "executionMode": "PAPER_TRADING_REAL_MARKET_DATA",
            "lastRun": timestamp(),
            "btcGuard": self.btc_guard_status,
            "activeSlotsCount": len(self.active_slots),
            "maxSlots": MAX_SLOTS,
            "totalWins": self.total_wins,
            "totalLosses": self.total_losses,
            "winRate": round(win_rate, 1),
            "netPnlUsd": round(total_net_pnl, 2),
            "realizedPnlUsd": round(self.net_pnl_usd, 2),
            "floatingPnlUsd": round(floating_pnl_usd, 2),
            "totalEquityUsd": round(total_equity, 2),
            "operating_capital_usd": round(self.operating_capital_usd, 2),
            "capitalModel": {
                "operating_100": round(self.operating_capital_usd, 2),
                "compounded_70": round(self.reinvested_70_usd, 2),
                "buffer_20": round(self.drawdown_buffer_usd, 2),
                "vault_10": round(self.profit_vault_usd, 2)
            },
            "active_slots": self.active_slots,
            "trade_history": self.trade_history
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def update_open_slots(self, current_analyses):
        """Monitorea los slots activos con simulación de OCO Server-Side + Trailing Escalonado"""
        price_dict = {a["ticker"]: a["price"] for a in current_analyses if a["price"] > 0}
        
        remaining_slots = []
        for slot in self.active_slots:
            ticker = slot["ticker"]
            entry_price = slot["entry_price"]
            current_price = price_dict.get(ticker, entry_price)

            # P&L Bruto y P&L Neto descontando comisiones de Binance (Entrada + Salida = 0.15%)
            raw_pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
            net_pnl_pct = raw_pnl_pct - (BINANCE_FEE_PCT * 2)

            slot["current_price"] = current_price
            slot["pnl_pct"] = round(net_pnl_pct, 2)
            slot["pnl_usd"] = round(CAPITAL_PER_SLOT_USD * (net_pnl_pct / 100.0), 2)

            # 1. Trailing Stop - Escalón 1 (+3.0% -> Mover SL a Breakeven +0.2%)
            if raw_pnl_pct >= TRAILING_STAGE_1 and slot.get("trailing_stage", 0) < 1:
                slot["trailing_stage"] = 1
                slot["stop_loss_pct"] = -0.2 # Breakeven positivo (cubre comisión)
                log_message("OCO_TRAIL", f"🔒 TRAILING 1 [{ticker}]: Ganancia al +{raw_pnl_pct:.2f}%. Stop OCO elevado a Breakeven (+0.2%).")

            # 2. Trailing Stop - Escalón 2 (+4.5% -> Mover SL a +2.5% Lock)
            elif raw_pnl_pct >= TRAILING_STAGE_2 and slot.get("trailing_stage", 0) < 2:
                slot["trailing_stage"] = 2
                slot["stop_loss_pct"] = -2.5 # Asegura ganancia neta de +2.5%
                log_message("OCO_TRAIL", f"🔥 TRAILING 2 [{ticker}]: Ganancia al +{raw_pnl_pct:.2f}%. Stop OCO elevado a +2.5% Ganancia Asegurada.")

            # 3. Check OCO Take Profit (+6.0%)
            if raw_pnl_pct >= TAKE_PROFIT_PCT:
                self.close_slot(slot, "OCO_TAKE_PROFIT", net_pnl_pct)
            # 4. Check OCO Stop Loss (Disparado en Servidor)
            elif raw_pnl_pct <= slot.get("stop_loss_pct", -STOP_LOSS_PCT):
                self.close_slot(slot, "OCO_STOP_LOSS", net_pnl_pct)
            else:
                remaining_slots.append(slot)

        self.active_slots = remaining_slots

    def close_slot(self, slot, reason, final_net_pnl_pct):
        pnl_usd = CAPITAL_PER_SLOT_USD * (final_net_pnl_pct / 100.0)
        self.net_pnl_usd += pnl_usd

        # Aplicar Regla de Reinversión 70 / 20 / 10 sobre la utilidad generada
        if pnl_usd > 0:
            self.total_wins += 1
            tag = "WIN 🎯"
            # 70% al Capital Operativo Compuesto
            self.reinvested_70_usd += pnl_usd * 0.70
            self.operating_capital_usd += pnl_usd * 0.70
            # 20% al Cojín de Reserva de Drawdown
            self.drawdown_buffer_usd += pnl_usd * 0.20
            # 10% a la Bóveda de Utilidad Intacta
            self.profit_vault_usd += pnl_usd * 0.10
        else:
            self.total_losses += 1
            tag = "LOSS 🛑"
            # Las pérdidas se absorben primero del Cojín de Reserva (20%) si hay fondo, protegiendo el capital compuesto
            if self.drawdown_buffer_usd >= abs(pnl_usd):
                self.drawdown_buffer_usd += pnl_usd
            else:
                remaining_loss = abs(pnl_usd) - self.drawdown_buffer_usd
                self.drawdown_buffer_usd = 0.0
                self.operating_capital_usd -= remaining_loss

        log_message("CLOSE_OCO", f"POSICIÓN CERRADA [{tag}]: [{slot['ticker']}] Motivo: {reason}. P&L Neto: {final_net_pnl_pct:+.2f}% (${pnl_usd:+.2f} USD).")

        total_equity = self.operating_capital_usd + self.drawdown_buffer_usd + self.profit_vault_usd
        self.telegram.notify_close_slot(slot, reason, final_net_pnl_pct, pnl_usd, total_equity)

        self.trade_history.insert(0, {
            "timestamp": timestamp(),
            "ticker": slot["ticker"],
            "name": slot["name"],
            "entry_price": slot["entry_price"],
            "exit_price": slot["current_price"],
            "pnl_pct": round(final_net_pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 2),
            "reason": reason,
            "result": "WIN" if final_net_pnl_pct > 0 else "LOSS"
        })

    def open_new_slots(self, ranked_analyses):
        """Ocupa los slots libres buscando patrones de Absorción de Volumen si BTC Guard está NORMAL"""
        if self.btc_guard_status["status"] == "PANIC_LOCK":
            log_message("BTC_GUARD", "⚠️ BLOQUEO DE APERTURA: BTC Guard está en PANIC_LOCK. No se abrirán nuevos slots.")
            self.telegram.notify_btc_guard(self.btc_guard_status["reason"])
            return

        open_tickers = {s["ticker"] for s in self.active_slots}
        free_slots = MAX_SLOTS - len(self.active_slots)

        if free_slots <= 0:
            return

        for analysis in ranked_analyses:
            ticker = analysis["ticker"]
            score = analysis["score"]

            # Requiere Score >= 68.0 (Señales de Absorción de Volumen)
            if ticker not in open_tickers and score >= 68.0 and analysis["price"] > 0:
                new_slot = {
                    "id": int(time.time() * 1000),
                    "ticker": ticker,
                    "name": analysis["name"],
                    "entry_time": timestamp(),
                    "entry_price": analysis["price"],
                    "current_price": analysis["price"],
                    "take_profit_pct": TAKE_PROFIT_PCT,
                    "stop_loss_pct": -STOP_LOSS_PCT,
                    "trailing_stage": 0,
                    "pnl_pct": 0.0,
                    "pnl_usd": 0.0,
                    "score": score,
                    "signal": analysis["signal"]
                }

                self.active_slots.append(new_slot)
                open_tickers.add(ticker)
                free_slots -= 1

                log_message("OPEN_OCO", f"NUEVO SLOT OCO ABIERTO (Slot #{len(self.active_slots)}): [{ticker}] a ${analysis['price']} (Score Absorción: {score}). OCO: TP +6%, SL -2%.")
                self.telegram.notify_open_slot(new_slot)

                if free_slots <= 0:
                    break

    def run_cycle(self):
        log_message("INFO", "--- ESCANEANDO TOP 20 Y EVALUANDO SLOTS DE PAPER TRADING ---")
        ranked_analyses, btc_status = self.analyzer.rank_top_20(self.top_20_list)
        self.btc_guard_status = btc_status
        
        self.update_open_slots(ranked_analyses)
        self.open_new_slots(ranked_analyses)
        self.save_state()
        
        return ranked_analyses

def main():
    log_message("INFO", "=== BOT CRIPTO PAPER TRADING EN VIVO (OCO SERVER-SIDE + BTC GUARD + REINVERSION 70-20-10) ===")
    engine = BinanceBotEngine()

    try:
        while True:
            engine.run_cycle()
            time.sleep(10)
    except KeyboardInterrupt:
        log_message("WARN", "Bot Cripto detenido.")

if __name__ == "__main__":
    main()
