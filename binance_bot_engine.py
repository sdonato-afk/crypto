# binance_bot_engine.py - Motor de Trading Multi-Posición (10 Slots Simultáneos - Escenario 3 Definitivo)
# Arquitectura: Paper Trading Top 50-100 / Entrada 50%+10% Escalonada / OCO TP +9% SL -4% / Trailing / Reinversión 70-20-10

import time
import json
import os
import random
from datetime import datetime
from crypto_analyzer import CryptoAnalyzer
from telegram_notifier import TelegramNotifier
from binance_client import BinanceClient
import urllib.request
import sys

DRY_RUN = True  # MODO SEGURO: True = Test-Net (Sin dinero real), False = LIVE TRADING

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ─── Limitar tamaño del log para evitar que el disco de Render se llene ─────
def trim_log_if_needed(log_file, max_lines=3000):
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            if len(lines) > max_lines:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-max_lines:])
    except Exception:
        pass

STATE_FILE = os.environ.get("STATE_FILE_NAME", "cripto_bot_estado.json")
LOG_FILE = "cripto_bot_ejecucion.log"
trim_log_if_needed(LOG_FILE)

# ─── AUTO-CONFIGURACIÓN INTELIGENTE SEGÚN EL NOMBRE DEL SERVICIO EN RENDER ───
raw_name = os.environ.get("RENDER_SERVICE_NAME", "").lower()
service_name = raw_name.replace("-", "").replace("_", "").strip()

# Perfil por defecto: NODO A (Conservador / Top 1-50 / DCA / Score 72)
profile = {
    "UNIVERSE_START": 1,
    "UNIVERSE_END": 50,
    "MIN_SCORE_ENTRY": 72.0,
    "ENTRY_PCT": 0.50,
    "SCALE_IN_PCT": 0.10,
    "STOP_LOSS_PCT": 4.0,
    "TAKE_PROFIT_PCT": 9.0,
    "INITIAL_CAPITAL_USD": 2500.0,
    "TRAILING_STAGE_1": 4.0,
    "TRAILING_STAGE_1_LOCK": 1.5,
    "TRAILING_STAGE_2": 6.5,
    "TRAILING_STAGE_2_LOCK": 4.0,
    "TRAILING_LOCK_EXIT": 3.9,
    "BREAKEVEN_EXIT": 1.5
}

# Perfil NODO B: (Render 3, 4, 7 -> Agresivo / Top 51-100 / All-In / Score 68 / TP 12 / SL 7)
if any(k in service_name for k in ["nodo3", "nodo4", "nodo7", "nodob", "exotico", "g6gq"]):
    profile.update({
        "UNIVERSE_START": 51,
        "UNIVERSE_END": 100,
        "MIN_SCORE_ENTRY": 68.0,
        "ENTRY_PCT": 1.0,
        "SCALE_IN_PCT": 0.0,
        "STOP_LOSS_PCT": 7.0,
        "TAKE_PROFIT_PCT": 12.0,
        "TRAILING_STAGE_1": 4.0,
        "TRAILING_STAGE_1_LOCK": 2.5,
        "TRAILING_STAGE_2": 6.5,
        "TRAILING_STAGE_2_LOCK": 5.0,
        "TRAILING_LOCK_EXIT": 4.8,
        "BREAKEVEN_EXIT": 2.5
    })
# Perfil NODO C: (Render 5, 8 -> Homologado a Swing 4H / Top 1-75 / TP 10% / SL 5.5% / Score 68)
elif any(k in service_name for k in ["nodo5", "nodo8", "nodoc", "rebote", "fo30", "uk8f"]):
    profile.update({
        "UNIVERSE_START": 1,
        "UNIVERSE_END": 75,
        "MIN_SCORE_ENTRY": 68.0,
        "ENTRY_PCT": 0.50,
        "SCALE_IN_PCT": 0.10,
        "STOP_LOSS_PCT": 5.5,
        "TAKE_PROFIT_PCT": 10.0,
        "TRAILING_STAGE_1": 4.0,
        "TRAILING_STAGE_1_LOCK": 2.0,
        "TRAILING_STAGE_2": 6.5,
        "TRAILING_STAGE_2_LOCK": 4.5,
        "TRAILING_LOCK_EXIT": 4.4,
        "BREAKEVEN_EXIT": 2.0
    })
elif "nodo2" in service_name:
    profile["MIN_SCORE_ENTRY"] = 70.0

MAX_SLOTS = 10
TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", profile["TAKE_PROFIT_PCT"]))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", profile["STOP_LOSS_PCT"]))
TRAILING_STAGE_1 = float(os.environ.get("TRAILING_STAGE_1", profile["TRAILING_STAGE_1"]))
TRAILING_STAGE_1_LOCK = float(os.environ.get("TRAILING_STAGE_1_LOCK", profile["TRAILING_STAGE_1_LOCK"]))
TRAILING_STAGE_2 = float(os.environ.get("TRAILING_STAGE_2", profile["TRAILING_STAGE_2"]))
TRAILING_STAGE_2_LOCK = float(os.environ.get("TRAILING_STAGE_2_LOCK", profile["TRAILING_STAGE_2_LOCK"]))
TRAILING_LOCK_EXIT = float(os.environ.get("TRAILING_LOCK_EXIT", profile["TRAILING_LOCK_EXIT"]))
BREAKEVEN_EXIT = float(os.environ.get("BREAKEVEN_EXIT", profile["BREAKEVEN_EXIT"]))
BINANCE_FEE_PCT = 0.024 # Tarifas optimizadas con descuento BNB + Maker Limit Orders + Kickback

INITIAL_CAPITAL_USD = float(os.environ.get("INITIAL_CAPITAL_USD", profile["INITIAL_CAPITAL_USD"]))
ENTRY_PCT = float(os.environ.get("ENTRY_PCT", profile["ENTRY_PCT"]))
SCALE_IN_PCT = float(os.environ.get("SCALE_IN_PCT", profile["SCALE_IN_PCT"]))
MIN_SCORE_ENTRY = float(os.environ.get("MIN_SCORE_ENTRY", profile["MIN_SCORE_ENTRY"]))
COOLDOWN_REENTRY_SEC = float(os.environ.get("COOLDOWN_REENTRY_SEC", 3600))
COOLDOWN_STOP_LOSS_SEC = float(os.environ.get("COOLDOWN_STOP_LOSS_SEC", 86400)) # 24 Horas tras Stop Loss
COOLDOWN_SCALE_IN_SEC = float(os.environ.get("COOLDOWN_SCALE_IN_SEC", 300))

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
        self.client = BinanceClient(os.getenv("BINANCE_API_KEY", ""), os.getenv("BINANCE_API_SECRET", ""), dry_run=DRY_RUN)
        self.active_slots = []
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        
        self.operating_capital_usd = INITIAL_CAPITAL_USD
        self.reinvested_70_usd = 0.0
        self.drawdown_buffer_usd = 0.0
        self.profit_vault_usd = 0.0
        self.net_pnl_usd = 0.0
        self.last_closed_timestamps = {} # ticker: timestamp epoch
        self.last_stop_loss_timestamps = {} # ticker: timestamp epoch (24h Cooldown)

        self.btc_guard_status = {"status": "NORMAL", "reason": "Iniciando bot", "drop_pct": 0.0}
        self.load_state()

    def _calculate_capital_model(self):
        """Calcula el modelo de capital 70-20-10 a partir del historial de trades"""
        win_profits = sum(t.get("pnl_usd", 0.0) for t in self.trade_history if t.get("pnl_usd", 0.0) > 0)
        loss_totals = abs(sum(t.get("pnl_usd", 0.0) for t in self.trade_history if t.get("pnl_usd", 0.0) < 0))

        reinvested_70 = round(win_profits * 0.70, 2)
        vault_10 = round(win_profits * 0.10, 2)
        potential_buffer = win_profits * 0.20

        if potential_buffer >= loss_totals:
            buffer_20 = round(potential_buffer - loss_totals, 2)
            unabsorbed_loss = 0.0
        else:
            buffer_20 = 0.0
            unabsorbed_loss = loss_totals - potential_buffer

        operating_capital = round(INITIAL_CAPITAL_USD + reinvested_70 - unabsorbed_loss, 2)

        return {
            "operating_capital": operating_capital,
            "reinvested_70": reinvested_70,
            "buffer_20": buffer_20,
            "vault_10": vault_10
        }

    def _execute_scale_in(self, slot, slot_base, entry_price, current_price, reason):
        """Ejecuta una recompra de 10% del slot (DCA o Piramidación)"""
        add_cost = slot_base * SCALE_IN_PCT
        add_qty = add_cost / current_price
        
        # Ejecución real en Binance (MARKET)
        success = self.client.place_market_order(slot["symbol"], "BUY", add_qty)
        if not success and not DRY_RUN:
            log_message("ERROR", f"Fallo al ejecutar SCALE_IN en Binance para {slot['symbol']}")
            return

        slot["total_spent"] = slot.get("total_spent", slot_base * ENTRY_PCT) + add_cost
        slot["total_qty"] = slot.get("total_qty", (slot_base * ENTRY_PCT) / entry_price) + add_qty
        slot["avg_entry_price"] = slot["total_spent"] / slot["total_qty"]
        slot["allocated_pct"] = slot.get("allocated_pct", ENTRY_PCT) + SCALE_IN_PCT
        slot["last_scale_timestamp"] = time.time()
        ticker = slot["ticker"]
        if reason == "DCA":
            log_message("SCALE_IN", f"➕ RECOMPRA DCA 10% [{ticker}]: Nuevo precio promedio: ${slot['avg_entry_price']:.4f} USD.")
        else:
            log_message("SCALE_IN", f"🚀 PIRAMIDACIÓN MOMENTUM 10% [{ticker}]: Carga incrementada. Precio promedio: ${slot['avg_entry_price']:.4f} USD.")

    def load_state(self):
        current_u_start = int(os.environ.get("UNIVERSE_START", 50))
        current_u_end   = int(os.environ.get("UNIVERSE_END", 100))

        # Si FRESH_START=1, limpiar estado viejo
        if os.environ.get("FRESH_START", "0") == "1":
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            log_message("INFO", "FRESH_START activado: estado anterior borrado. Arrancando desde cero.")
            return

        data = None
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

        # Auto-deteccion: si el universo guardado no coincide con el actual, limpiar
        if data:
            saved_u_start = data.get("universe_start", -1)
            saved_u_end   = data.get("universe_end", -1)
            if saved_u_start != current_u_start or saved_u_end != current_u_end:
                log_message("INFO", f"Universo cambio ({saved_u_start}-{saved_u_end} -> {current_u_start}-{current_u_end}). Limpiando estado anterior automaticamente.")
                data = None

        # Nota: No cargamos estado desde GitHub en la nube para evitar que nodos
        # compartan posiciones erróneas. Cada nodo arranca desde cero de forma segura.

        if data:
            self.active_slots = data.get("active_slots", [])
            self.trade_history = data.get("trade_history", [])
            self.total_wins = sum(1 for t in self.trade_history if t.get("result") == "WIN")
            self.total_losses = sum(1 for t in self.trade_history if t.get("result") == "LOSS")
            self.realized_pnl_usd = sum(t.get("pnl_usd", 0.0) for t in self.trade_history)

            real_balance = self.client.get_usdt_balance()
            if real_balance > 0:
                self.operating_capital_usd = real_balance
                log_message("INFO", f"Sincronizado balance real con Binance: ${real_balance:.2f} USDT")
            else:
                cap = self._calculate_capital_model()
                self.operating_capital_usd = cap["operating_capital"]

            cap = self._calculate_capital_model()
            self.reinvested_70_usd = cap["reinvested_70"]
            self.profit_vault_usd = cap["vault_10"]
            self.drawdown_buffer_usd = cap["buffer_20"]
            log_message("INFO", f"Estado cargado: {self.total_wins} Wins / {self.total_losses} Losses | Capital de Operacion: ${self.operating_capital_usd:.2f} USD")

    def save_state(self):
        self.total_wins = sum(1 for t in self.trade_history if t.get("result") == "WIN")
        self.total_losses = sum(1 for t in self.trade_history if t.get("result") == "LOSS")

        total_trades = self.total_wins + self.total_losses
        win_rate = (self.total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
        
        realized_pnl = sum(t.get("pnl_usd", 0.0) for t in self.trade_history)
        
        for slot in self.active_slots:
            if "allocated_capital_usd" not in slot:
                slot["allocated_capital_usd"] = round(self.operating_capital_usd / MAX_SLOTS, 2)

        floating_pnl = sum(slot.get("pnl_usd", 0.0) for slot in self.active_slots)
        gross_assets = sum(slot.get("allocated_capital_usd", 100.0) + slot.get("pnl_usd", 0.0) for slot in self.active_slots)
        
        total_net_pnl = realized_pnl + floating_pnl
        total_equity = INITIAL_CAPITAL_USD + total_net_pnl

        cap = self._calculate_capital_model()
        reinvested_70 = cap["reinvested_70"]
        vault_10 = cap["vault_10"]
        buffer_20 = cap["buffer_20"]
        operating_capital = cap["operating_capital"]

        state = {
            "botStatus": "PAPER_TRADING_TOP50_100_ACTIVO",
            "executionMode": "PAPER_TRADING_REAL_MARKET_DATA",
            "universe_start": int(os.environ.get("UNIVERSE_START", profile["UNIVERSE_START"])),
            "universe_end": int(os.environ.get("UNIVERSE_END", profile["UNIVERSE_END"])),
            "lastRun": timestamp(),
            "btcGuard": self.btc_guard_status,
            "activeSlotsCount": len(self.active_slots),
            "maxSlots": MAX_SLOTS,
            "totalWins": self.total_wins,
            "totalLosses": self.total_losses,
            "winRate": round(win_rate, 1),
            "netPnlUsd": round(total_net_pnl, 2),
            "realizedPnlUsd": round(realized_pnl, 2),
            "floatingPnlUsd": round(floating_pnl, 2),
            "grossAssetsUsd": round(gross_assets, 2),
            "totalEquityUsd": round(total_equity, 2),
            "operating_capital_usd": operating_capital,
            "capitalModel": {
                "operating_100": operating_capital,
                "compounded_70": reinvested_70,
                "buffer_20": buffer_20,
                "vault_10": vault_10
            },
            "active_slots": self.active_slots,
            "trade_history": self.trade_history
        }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def update_open_slots(self, current_analyses):
        """Monitorea los slots con Escalonamiento 50%+10%, Trailing y P&L Dinámico"""
        price_dict = {a["ticker"]: a["price"] for a in current_analyses if a["price"] > 0}
        
        remaining_slots = []
        for slot in self.active_slots:
            ticker = slot["ticker"]
            entry_price = slot.get("avg_entry_price", slot["entry_price"])
            current_price = price_dict.get(ticker, 0.0)
            if current_price <= 0:
                # Ticker salió del Top 50-100, consultar precio directo a Binance
                current_price = self.analyzer.fetch_ticker_price(slot.get("symbol", ticker + "USDT"))
                if current_price <= 0:
                    current_price = entry_price  # Último recurso si API falla

            raw_pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
            net_pnl_pct = raw_pnl_pct - (BINANCE_FEE_PCT * 2)

            slot_base = slot.get("allocated_capital_usd", round(self.operating_capital_usd / MAX_SLOTS, 2))
            allocated_pct = slot.get("allocated_pct", ENTRY_PCT)

            # Escalonamiento del 10% adicional en Dips (-1.2%) o Momentum (+2.0%)
            last_scale = slot.get("last_scale_timestamp", 0)
            scale_cooldown_ok = (time.time() - last_scale) >= COOLDOWN_SCALE_IN_SEC

            if net_pnl_pct <= -1.2 and allocated_pct < 1.0 and scale_cooldown_ok:
                self._execute_scale_in(slot, slot_base, entry_price, current_price, "DCA")
            elif net_pnl_pct >= 2.0 and allocated_pct < 1.0 and net_pnl_pct < 7.0 and scale_cooldown_ok:
                self._execute_scale_in(slot, slot_base, entry_price, current_price, "MOMENTUM")

            slot["current_price"] = current_price
            slot["pnl_pct"] = round(net_pnl_pct, 2)
            slot["pnl_usd"] = round(slot.get("total_spent", slot_base * ENTRY_PCT) * (net_pnl_pct / 100.0), 2)

            trailing_stage = slot.get("trailing_stage", 0)

            # Trailing Stop Escalonado
            if net_pnl_pct >= TRAILING_STAGE_1 and trailing_stage < 1:
                slot["trailing_stage"] = 1
                log_message("OCO_TRAIL", f"🔒 TRAILING 1 [{ticker}]: Ganancia al +{net_pnl_pct:.2f}%. Stop elevado a Breakeven (+{BREAKEVEN_EXIT}%).")
            if net_pnl_pct >= TRAILING_STAGE_2 and slot.get("trailing_stage", 0) < 2:
                slot["trailing_stage"] = 2
                log_message("OCO_TRAIL", f"🔥 TRAILING 2 [{ticker}]: Ganancia al +{net_pnl_pct:.2f}%. Stop elevado a Lock (+{TRAILING_LOCK_EXIT}%).")

            current_stage = slot.get("trailing_stage", 0)

            # Cierres
            if net_pnl_pct >= TAKE_PROFIT_PCT:
                self.close_slot(slot, "OCO_TAKE_PROFIT", net_pnl_pct)
            elif current_stage == 2 and net_pnl_pct <= TRAILING_LOCK_EXIT:
                self.close_slot(slot, "TRAILING_LOCK_4PCT", net_pnl_pct)
            elif current_stage == 1 and net_pnl_pct <= BREAKEVEN_EXIT:
                self.close_slot(slot, "TRAILING_BREAKEVEN", net_pnl_pct)
            elif current_stage == 0 and net_pnl_pct <= -STOP_LOSS_PCT:
                self.close_slot(slot, "OCO_STOP_LOSS", net_pnl_pct)
            else:
                remaining_slots.append(slot)

        self.active_slots = remaining_slots

    def close_slot(self, slot, reason, final_net_pnl_pct):
        # Cancelar cualquier orden OCO pendiente
        self.client.cancel_all_orders(slot["symbol"])
        # Ejecutar Market Sell
        self.client.close_market(slot["symbol"], slot["total_qty"])

        total_spent = slot.get("total_spent", (slot.get("allocated_capital_usd", 100.0) * ENTRY_PCT))
        pnl_usd = total_spent * (final_net_pnl_pct / 100.0)
        self.net_pnl_usd += pnl_usd

        if pnl_usd > 0:
            self.total_wins += 1
            tag = "WIN 🎯"
            self.reinvested_70_usd += pnl_usd * 0.70
            self.operating_capital_usd += pnl_usd * 0.70
            self.drawdown_buffer_usd += pnl_usd * 0.20
            self.profit_vault_usd += pnl_usd * 0.10
        else:
            self.total_losses += 1
            tag = "LOSS 🛑"
            if self.drawdown_buffer_usd >= abs(pnl_usd):
                self.drawdown_buffer_usd += pnl_usd
            else:
                remaining_loss = abs(pnl_usd) - self.drawdown_buffer_usd
                self.drawdown_buffer_usd = 0.0
                self.operating_capital_usd -= remaining_loss

        self.last_closed_timestamps[slot["ticker"]] = time.time()
        if final_net_pnl_pct <= 0 or "STOP_LOSS" in reason:
            self.last_stop_loss_timestamps[slot["ticker"]] = time.time()
            log_message("COOLDOWN", f"🛑 Cooldown de 24h activado para [{slot['ticker']}] tras Stop Loss.")

        log_message("CLOSE_OCO", f"POSICIÓN CERRADA [{tag}]: [{slot['ticker']}] Motivo: {reason}. P&L Neto: {final_net_pnl_pct:+.2f}% (${pnl_usd:+.2f} USD).")
        total_equity = self.operating_capital_usd + self.drawdown_buffer_usd + self.profit_vault_usd
        self.telegram.notify_close_slot(slot, reason, final_net_pnl_pct, pnl_usd, total_equity)

        self.trade_history.insert(0, {
            "timestamp": timestamp(),
            "ticker": slot["ticker"],
            "name": slot["name"],
            "entry_price": slot.get("avg_entry_price", slot["entry_price"]),
            "exit_price": slot["current_price"],
            "pnl_pct": round(final_net_pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 2),
            "reason": reason,
            "result": "WIN" if final_net_pnl_pct > 0 else "LOSS"
        })

    def execute_iceberg_order(self, ticker, total_usd_spent, base_price, chunk_size_usd=200.0):
        """
        Módulo Iceberg: Si el monto de entrada supera $300 USD, lo fragmenta
        en micro-compras de ~$200 USD con pausas aleatorias (1.2s a 3.5s)
        para ocultar el footprint en el libro de órdenes y eliminar el slippage.
        """
        if total_usd_spent <= 300.0:
            qty = total_usd_spent / base_price
            return base_price, qty, total_usd_spent

        chunks = []
        remaining = total_usd_spent
        while remaining > 0:
            current_chunk = min(chunk_size_usd, remaining)
            chunks.append(current_chunk)
            remaining -= current_chunk

        log_message("ICEBERG", f"🧊 [EJECUCIÓN ICEBERG ACTIVADA] [{ticker}]: ${total_usd_spent:.2f} USD divididos en {len(chunks)} micro-compras de ~${chunk_size_usd} USD.")

        total_qty = 0.0
        spent_accum = 0.0

        for i, chunk_usd in enumerate(chunks):
            micro_price = base_price * (1.0 + random.uniform(-0.0003, 0.0015))
            micro_qty = chunk_usd / micro_price
            total_qty += micro_qty
            spent_accum += chunk_usd

            symbol = (ticker + "USDT") if not ticker.endswith("USDT") else ticker
            if not DRY_RUN:
                chunk_success = self.client.place_market_order(symbol, "BUY", micro_qty)
                if not chunk_success:
                    log_message("ERROR", f"Fallo orden fragmento ICEBERG {i+1} en Binance para {ticker}")

            if i < len(chunks) - 1:
                delay = round(random.uniform(1.2, 3.5), 2)
                log_message("ICEBERG", f"   ↳ Fragmento {i+1}/{len(chunks)} [{ticker}]: ${chunk_usd:.2f} USD a ${micro_price:.4f}. Pausa táctica de {delay}s...")
                time.sleep(delay)

        avg_entry_price = spent_accum / total_qty
        log_message("ICEBERG", f"✅ [ICEBERG COMPLETADO] [{ticker}]: Entrada total de ${spent_accum:.2f} USD ejecutada desincronizada. Precio Promedio: ${avg_entry_price:.4f}")
        return avg_entry_price, total_qty, spent_accum

    def _get_dynamic_blacklist(self):
        """
        Escanea el historial de trades del nodo y bloquea dinámicamente activos con performance tóxica:
        - Criptos con 3 o más pérdidas sin ninguna victoria
        - Criptos con Win Rate <= 15% tras al menos 3 trades
        """
        toxic = set()
        asset_history = {}
        for t in reversed(self.trade_history):
            ticker = t.get("ticker")
            if not ticker: continue
            if ticker not in asset_history:
                asset_history[ticker] = []
            asset_history[ticker].append(t.get("result", "LOSS"))
        
        for ticker, results in asset_history.items():
            wins = sum(1 for r in results if r == "WIN")
            losses = sum(1 for r in results if r == "LOSS")
            if (losses >= 3 and wins == 0) or (len(results) >= 3 and (wins / len(results)) <= 0.15):
                toxic.add(ticker)
        return toxic

    def open_new_slots(self, ranked_analyses):
        """Ocupa los slots libres buscando patrones de Absorción + Geometría en el Top 50-100"""
        if self.btc_guard_status["status"] == "PANIC_LOCK":
            log_message("BTC_GUARD", "⚠️ BLOQUEO DE APERTURA: BTC Guard en PANIC_LOCK.")
            self.telegram.notify_btc_guard(self.btc_guard_status["reason"])
            return

        open_tickers = {s["ticker"] for s in self.active_slots}
        free_slots = MAX_SLOTS - len(self.active_slots)

        if free_slots <= 0:
            return

        now = time.time()
        dynamic_toxic = self._get_dynamic_blacklist()

        for analysis in ranked_analyses:
            ticker = analysis["ticker"]
            score = analysis["score"]

            if ticker in dynamic_toxic:
                log_message("BLACKLIST_DINAMICA", f"⛔ BLOQUEO AUTOMÁTICO [{ticker}]: Excluido dinámicamente por historial de pérdidas tóxicas.")
                continue

            # Cooldown de 24 horas tras Stop Loss para evitar re-entradas impulsivas en caídas
            last_sl = self.last_stop_loss_timestamps.get(ticker, 0)
            if (now - last_sl) < COOLDOWN_STOP_LOSS_SEC:
                continue

            # Cooldown habitual de 60 minutos por moneda
            last_closed = self.last_closed_timestamps.get(ticker, 0)
            if (now - last_closed) < COOLDOWN_REENTRY_SEC:
                continue

            if ticker not in open_tickers and score >= MIN_SCORE_ENTRY and analysis["price"] > 0:
                slot_capital = round(self.operating_capital_usd / MAX_SLOTS, 2)
                initial_entry_cost = round(slot_capital * ENTRY_PCT, 2)
                
                avg_entry_price, total_qty, total_spent = self.execute_iceberg_order(ticker, initial_entry_cost, analysis["price"])

                new_slot = {
                    "id": f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
                    "ticker": ticker,
                    "name": analysis["name"],
                    "symbol": analysis["symbol"],
                    "entry_time": timestamp(),
                    "entry_price": analysis["price"],
                    "avg_entry_price": avg_entry_price,
                    "current_price": analysis["price"],
                    "allocated_capital_usd": slot_capital,
                    "total_spent": total_spent,
                    "total_qty": total_qty,
                    "allocated_pct": ENTRY_PCT,
                    "take_profit_pct": TAKE_PROFIT_PCT,
                    "stop_loss_pct": -STOP_LOSS_PCT,
                    "trailing_stage": 0,
                    "pnl_pct": 0.0,
                    "pnl_usd": 0.0,
                    "score": score,
                    "signal": analysis["signal"]
                }

                # Ejecutar OCO Real
                tp_price = avg_entry_price * (1 + (TAKE_PROFIT_PCT / 100))
                sl_price = avg_entry_price * (1 - (STOP_LOSS_PCT / 100))
                self.client.place_oco_order(analysis["symbol"], total_qty, tp_price, sl_price, sl_price)

                self.active_slots.append(new_slot)
                open_tickers.add(ticker)
                free_slots -= 1

                log_message("OPEN_OCO", f"NUEVO SLOT ESCALONADO 50% ABIERTO (Slot #{len(self.active_slots)}): [{ticker}] a ${avg_entry_price:.4f} (Base Slot: ${slot_capital} USD). Entrada 50%: ${total_spent} USD. TP +9%, SL -4%.")
                self.telegram.notify_open_slot(new_slot)

                if free_slots <= 0:
                    break

    PENDING_CLOSES_FILE = "pending_closes.json"

    def process_manual_closes(self):
        """Lee el archivo de cierres manuales y cierra esas posiciones inmediatamente."""
        if not os.path.exists(self.PENDING_CLOSES_FILE):
            return
        try:
            with open(self.PENDING_CLOSES_FILE, "r") as f:
                tickers_to_close = json.load(f)
            if not tickers_to_close:
                return

            closed = []
            remaining_slots = []
            for slot in self.active_slots:
                if slot["ticker"] in tickers_to_close:
                    pnl_pct = round(slot.get("pnl_pct", 0.0), 2)
                    log_message("MANUAL_CLOSE", f"[{slot['ticker']}] procesando cierre manual desde Dashboard. PnL: {pnl_pct}%")
                    self.close_slot(slot, "MANUAL_CLOSE", pnl_pct)
                    closed.append(slot["ticker"])
                else:
                    remaining_slots.append(slot)

            self.active_slots = remaining_slots

            # Limpiar solo los que se cerraron; dejar los que no se encontraron por si acaso
            leftover = [t for t in tickers_to_close if t not in closed]
            if leftover:
                with open(self.PENDING_CLOSES_FILE, "w") as f:
                    json.dump(leftover, f)
            else:
                os.remove(self.PENDING_CLOSES_FILE)

        except Exception as e:
            log_message("WARN", f"process_manual_closes error: {e}")

    def run_cycle(self):
        try:
            log_message("INFO", "--- ESCANEANDO UNIVERSO Y EVALUANDO SLOTS ---")
            ranked_analyses, btc_status = self.analyzer.rank_universe()
            self.btc_guard_status = btc_status

            self.process_manual_closes()   # ← Cierres manuales del Dashboard
            self.update_open_slots(ranked_analyses)
            self.open_new_slots(ranked_analyses)
            self.save_state()
            
            return ranked_analyses
        except Exception as e:
            # ⚠️ Escudo Anti-Crash: cualquier excepción no mata el proceso,
            # el bot descansa 30 segundos y retoma el ciclo normalmente.
            log_message("WARN", f"Ciclo con error recuperable: {e}. Reintentando en 30s...")
            time.sleep(30)
            return []

def main():
    log_message("INFO", "=== BOT CRIPTO INICIANDO (ARQUITECTURA DUAL - MODO PAPEL) ===")
    log_message("INFO", f"Universo: [{os.environ.get('UNIVERSE_START','50')}-{os.environ.get('UNIVERSE_END','100')}] | TP: +{os.environ.get('TAKE_PROFIT_PCT','9')}% | SL: -{os.environ.get('STOP_LOSS_PCT','4')}%")
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
            wait = min(60 * consecutive_errors, 300)  # Backoff: 1min, 2min... máx 5min
            log_message("ERROR", f"Error crítico #{consecutive_errors} en loop principal: {e}. Esperando {wait}s antes de reintentar...")
            time.sleep(wait)

if __name__ == "__main__":
    main()
