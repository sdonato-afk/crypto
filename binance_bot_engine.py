# binance_bot_engine.py - Motor de Trading Multi-Posición (10 Slots Simultáneos - Escenario 3 Definitivo)
# Arquitectura: Paper Trading Top 50-100 / Entrada 50%+10% Escalonada / OCO TP +9% SL -4% / Trailing / Reinversión 70-20-10

import time
import json
import os
import random
from datetime import datetime
from crypto_analyzer import CryptoAnalyzer
from telegram_notifier import TelegramNotifier
import urllib.request
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

STATE_FILE = "cripto_bot_estado.json"
LOG_FILE = "cripto_bot_ejecucion.log"

MAX_SLOTS = 10
TAKE_PROFIT_PCT = 9.0
STOP_LOSS_PCT = 4.0
TRAILING_STAGE_1 = 4.0  # Mueve SL a Breakeven +0.3%
TRAILING_STAGE_2 = 6.5  # Mueve SL a +4.0% Lock de ganancia
BINANCE_FEE_PCT = 0.024 # Tarifas optimizadas con descuento BNB + Maker Limit Orders + Kickback

INITIAL_CAPITAL_USD = 1000.0

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
        self.total_wins = 0
        self.total_losses = 0
        
        self.operating_capital_usd = 1000.0
        self.reinvested_70_usd = 0.0
        self.drawdown_buffer_usd = 0.0
        self.profit_vault_usd = 0.0
        self.net_pnl_usd = 0.0
        self.last_closed_timestamps = {} # ticker: timestamp epoch

        self.btc_guard_status = {"status": "NORMAL", "reason": "Iniciando bot", "drop_pct": 0.0}
        self.load_state()

    def load_state(self):
        data = None
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

        if not data and "RENDER" in os.environ:
            try:
                raw_url = "https://raw.githubusercontent.com/sdonato-afk/crypto/main/cripto_bot_estado.json"
                req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    log_message("INFO", "Estado recuperado desde GitHub Cloud con éxito.")
            except Exception as e:
                log_message("WARN", f"No se pudo cargar estado remoto desde GitHub ({e})")

        if data:
            self.active_slots = data.get("active_slots", [])
            self.trade_history = data.get("trade_history", [])
            self.total_wins = sum(1 for t in self.trade_history if t.get("result") == "WIN")
            self.total_losses = sum(1 for t in self.trade_history if t.get("result") == "LOSS")
            self.realized_pnl_usd = sum(t.get("pnl_usd", 0.0) for t in self.trade_history)

            win_profits = sum(t.get("pnl_usd", 0.0) for t in self.trade_history if t.get("pnl_usd", 0.0) > 0)
            loss_totals = abs(sum(t.get("pnl_usd", 0.0) for t in self.trade_history if t.get("pnl_usd", 0.0) < 0))

            self.reinvested_70_usd = round(win_profits * 0.70, 2)
            self.profit_vault_usd = round(win_profits * 0.10, 2)
            potential_buffer = win_profits * 0.20
            
            if potential_buffer >= loss_totals:
                self.drawdown_buffer_usd = round(potential_buffer - loss_totals, 2)
                unabsorbed_loss = 0.0
            else:
                self.drawdown_buffer_usd = 0.0
                unabsorbed_loss = loss_totals - potential_buffer

            self.operating_capital_usd = round(INITIAL_CAPITAL_USD + self.reinvested_70_usd - unabsorbed_loss, 2)
            log_message("INFO", f"Estado cargado: {self.total_wins} Wins / {self.total_losses} Losses | PnL Realizado: ${self.realized_pnl_usd:.2f} USD")

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

        state = {
            "botStatus": "PAPER_TRADING_TOP50_100_ACTIVO",
            "executionMode": "PAPER_TRADING_REAL_MARKET_DATA",
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
            current_price = price_dict.get(ticker, entry_price)

            raw_pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
            net_pnl_pct = raw_pnl_pct - (BINANCE_FEE_PCT * 2)

            slot_base = slot.get("allocated_capital_usd", round(self.operating_capital_usd / MAX_SLOTS, 2))
            allocated_pct = slot.get("allocated_pct", 0.50)

            # Escalonamiento del 10% adicional en Dips (-1.2%) o Momentum (+2.0%)
            if net_pnl_pct <= -1.2 and allocated_pct < 1.0:
                add_cost = slot_base * 0.10
                add_qty = add_cost / current_price
                slot["total_spent"] = slot.get("total_spent", slot_base * 0.50) + add_cost
                slot["total_qty"] = slot.get("total_qty", (slot_base * 0.50) / entry_price) + add_qty
                slot["avg_entry_price"] = slot["total_spent"] / slot["total_qty"]
                slot["allocated_pct"] = allocated_pct + 0.10
                log_message("SCALE_IN", f"➕ RECOMPRA DCA 10% [{ticker}]: Nuevo precio promedio: ${slot['avg_entry_price']:.4f} USD.")
            elif net_pnl_pct >= 2.0 and allocated_pct < 1.0 and net_pnl_pct < 7.0:
                add_cost = slot_base * 0.10
                add_qty = add_cost / current_price
                slot["total_spent"] = slot.get("total_spent", slot_base * 0.50) + add_cost
                slot["total_qty"] = slot.get("total_qty", (slot_base * 0.50) / entry_price) + add_qty
                slot["avg_entry_price"] = slot["total_spent"] / slot["total_qty"]
                slot["allocated_pct"] = allocated_pct + 0.10
                log_message("SCALE_IN", f"🚀 PIRAMIDACIÓN MOMENTUM 10% [{ticker}]: Carga incrementada. Precio promedio: ${slot['avg_entry_price']:.4f} USD.")

            slot["current_price"] = current_price
            slot["pnl_pct"] = round(net_pnl_pct, 2)
            slot["pnl_usd"] = round(slot.get("total_spent", slot_base * 0.50) * (net_pnl_pct / 100.0), 2)

            trailing_stage = slot.get("trailing_stage", 0)

            # Trailing Stop Escalonado
            if net_pnl_pct >= TRAILING_STAGE_1 and trailing_stage < 1:
                slot["trailing_stage"] = 1
                log_message("OCO_TRAIL", f"🔒 TRAILING 1 [{ticker}]: Ganancia al +{net_pnl_pct:.2f}%. Stop elevado a Breakeven (+0.3%).")
            elif net_pnl_pct >= TRAILING_STAGE_2 and trailing_stage < 2:
                slot["trailing_stage"] = 2
                log_message("OCO_TRAIL", f"🔥 TRAILING 2 [{ticker}]: Ganancia al +{net_pnl_pct:.2f}%. Stop elevado a Lock (+4.0%).")

            current_stage = slot.get("trailing_stage", 0)

            # Cierres
            if net_pnl_pct >= TAKE_PROFIT_PCT:
                self.close_slot(slot, "OCO_TAKE_PROFIT", net_pnl_pct)
            elif current_stage == 2 and net_pnl_pct <= 4.0:
                self.close_slot(slot, "TRAILING_LOCK_4PCT", net_pnl_pct)
            elif current_stage == 1 and net_pnl_pct <= 0.3:
                self.close_slot(slot, "TRAILING_BREAKEVEN", net_pnl_pct)
            elif current_stage == 0 and net_pnl_pct <= -STOP_LOSS_PCT:
                self.close_slot(slot, "OCO_STOP_LOSS", net_pnl_pct)
            else:
                remaining_slots.append(slot)

        self.active_slots = remaining_slots

    def close_slot(self, slot, reason, final_net_pnl_pct):
        total_spent = slot.get("total_spent", (slot.get("allocated_capital_usd", 100.0) * 0.50))
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
            micro_price = base_price * (1.0 + random.uniform(-0.0001, 0.0002))
            micro_qty = chunk_usd / micro_price
            total_qty += micro_qty
            spent_accum += chunk_usd

            if i < len(chunks) - 1:
                delay = round(random.uniform(1.2, 3.5), 2)
                log_message("ICEBERG", f"   ↳ Fragmento {i+1}/{len(chunks)} [{ticker}]: ${chunk_usd:.2f} USD a ${micro_price:.4f}. Pausa táctica de {delay}s...")
                time.sleep(delay)

        avg_entry_price = spent_accum / total_qty
        log_message("ICEBERG", f"✅ [ICEBERG COMPLETADO] [{ticker}]: Entrada total de ${spent_accum:.2f} USD ejecutada desincronizada. Precio Promedio: ${avg_entry_price:.4f}")
        return avg_entry_price, total_qty, spent_accum

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

        for analysis in ranked_analyses:
            ticker = analysis["ticker"]
            score = analysis["score"]

            # Cooldown de 60 minutos (3600 segundos) por moneda
            last_closed = self.last_closed_timestamps.get(ticker, 0)
            if (now - last_closed) < 3600:
                continue

            if ticker not in open_tickers and score >= 68.0 and analysis["price"] > 0:
                slot_capital = round(self.operating_capital_usd / MAX_SLOTS, 2)
                initial_entry_cost = round(slot_capital * 0.50, 2)
                
                avg_entry_price, total_qty, total_spent = self.execute_iceberg_order(ticker, initial_entry_cost, analysis["price"])

                new_slot = {
                    "id": int(time.time() * 1000),
                    "ticker": ticker,
                    "name": analysis["name"],
                    "entry_time": timestamp(),
                    "entry_price": analysis["price"],
                    "avg_entry_price": avg_entry_price,
                    "current_price": analysis["price"],
                    "allocated_capital_usd": slot_capital,
                    "total_spent": total_spent,
                    "total_qty": total_qty,
                    "allocated_pct": 0.50,
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

                log_message("OPEN_OCO", f"NUEVO SLOT ESCALONADO 50% ABIERTO (Slot #{len(self.active_slots)}): [{ticker}] a ${avg_entry_price:.4f} (Base Slot: ${slot_capital} USD). Entrada 50%: ${total_spent} USD. TP +9%, SL -4%.")
                self.telegram.notify_open_slot(new_slot)

                if free_slots <= 0:
                    break

    def run_cycle(self):
        log_message("INFO", "--- ESCANEANDO TOP 50-100 Y EVALUANDO SLOTS DE PAPER TRADING ---")
        ranked_analyses, btc_status = self.analyzer.rank_top_20() # Top 50-100 dinámico
        self.btc_guard_status = btc_status
        
        self.update_open_slots(ranked_analyses)
        self.open_new_slots(ranked_analyses)
        self.save_state()
        
        return ranked_analyses

def main():
    log_message("INFO", "=== BOT CRIPTO DEFINTIVO TOP 50-100 (50%+10% ESCALONADO + GEOMETRIA + REINVERSION 70-20-10) ===")
    engine = BinanceBotEngine()

    try:
        while True:
            engine.run_cycle()
            time.sleep(10)
    except KeyboardInterrupt:
        log_message("WARN", "Bot Cripto detenido.")

if __name__ == "__main__":
    main()
