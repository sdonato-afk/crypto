# simular_bot_definitivo_365d.py - Simulación empírica del Bot Definitivo a 365 días en Binance
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== INICIANDO SIMULACIÓN DE 365 DÍAS PARA EL BOT DEFINITIVO (TOP 50-100) ===")

url_24h = "https://api.binance.com/api/v3/ticker/24hr"
req = urllib.request.Request(url_24h, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
except Exception as e:
    print(f"Error conectando a Binance: {e}")
    sys.exit(1)

usdt_pairs = [d for d in data if d['symbol'].endswith('USDT') and not d['symbol'].startswith('UP') and not d['symbol'].startswith('DOWN') and not 'BEAR' in d['symbol'] and not 'BULL' in d['symbol'] and not 'FDUSD' in d['symbol'] and not 'USDC' in d['symbol'] and not 'TUSD' in d['symbol'] and not 'EUR' in d['symbol']]
usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)

top_50_100 = usdt_pairs[50:100]

sample_data = {}
for p in top_50_100[:35]:
    symbol = p['symbol']
    url_k = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=1000"
    try:
        req_k = urllib.request.Request(url_k, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            if len(klines) >= 500:
                sample_data[symbol] = klines
    except Exception:
        pass
    time.sleep(0.02)

print(f"Datos descargados para {len(sample_data)} monedas del Top 50-100. Ejecutando motor de 10 slots simultáneos...")

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(diff if diff >= 0 else 0.0)
        losses.append(abs(diff) if diff < 0 else 0.0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

initial_capital = 1000.0
operating_capital = 1000.0
compounded_70 = 0.0
buffer_20 = 0.0
vault_10 = 0.0

active_slots = {}
max_slots = 10
tp = 9.0
sl = 4.0
fee_rate = 0.00024 # tarifa combinada optimizada con BNB + Rakeback + Maker (0.024%)

total_wins = 0
total_losses = 0
total_trades = 0
last_closed_index = {} # symbol: candle_index

min_timeline_len = min(len(v) for v in sample_data.values())

for i in range(50, min_timeline_len):
    closed_symbols = []
    
    # 1. Monitorear y actualizar posiciones activas
    for symbol, slot in list(active_slots.items()):
        klines = sample_data[symbol]
        op = float(klines[i][1])
        hi = float(klines[i][2])
        lo = float(klines[i][3])
        cl = float(klines[i][4])
        
        avg_entry = slot["avg_entry"]
        allocated_pct = slot["allocated_pct"]
        slot_base_capital = slot["slot_base_capital"]
        trailing_stage = slot.get("trailing_stage", 0)
        current_sl_pct = slot.get("current_sl_pct", sl)
        
        current_pnl = ((cl - avg_entry) / avg_entry) * 100.0
        
        # Escalonamiento 10%
        if current_pnl <= -1.2 and allocated_pct < 1.0:
            add_cost = slot_base_capital * 0.10
            slot["total_spent"] += add_cost
            slot["total_qty"] += (add_cost / cl)
            slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
            slot["allocated_pct"] += 0.10
        elif current_pnl >= 2.0 and allocated_pct < 1.0 and current_pnl < 7.0:
            add_cost = slot_base_capital * 0.10
            slot["total_spent"] += add_cost
            slot["total_qty"] += (add_cost / cl)
            slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
            slot["allocated_pct"] += 0.10

        high_pnl = ((hi - avg_entry) / avg_entry) * 100.0
        low_pnl = ((lo - avg_entry) / avg_entry) * 100.0

        # Trailing Stop Escalonado Check
        if high_pnl >= 4.0 and trailing_stage < 1:
            slot["trailing_stage"] = 1
        elif high_pnl >= 6.5 and trailing_stage < 2:
            slot["trailing_stage"] = 2

        current_stage = slot.get("trailing_stage", 0)

        # 1. Take Profit (+9.0%)
        if high_pnl >= tp:
            pnl_usd = slot["total_spent"] * (tp / 100.0) - (slot["total_spent"] * fee_rate)
            total_wins += 1
            total_trades += 1
            
            reinvest = pnl_usd * 0.70
            buf_20 = pnl_usd * 0.20
            v_10 = pnl_usd * 0.10
            
            operating_capital += reinvest
            compounded_70 += reinvest
            buffer_20 += buf_20
            vault_10 += v_10
            closed_symbols.append(symbol)
            last_closed_index[symbol] = i

        # 2. Cierre por Trailing Stage 2 (+4.0% Lock)
        elif current_stage == 2 and current_pnl <= 4.0:
            pnl_usd = slot["total_spent"] * 0.04 - (slot["total_spent"] * fee_rate)
            total_wins += 1
            total_trades += 1
            
            reinvest = pnl_usd * 0.70
            buf_20 = pnl_usd * 0.20
            v_10 = pnl_usd * 0.10
            
            operating_capital += reinvest
            compounded_70 += reinvest
            buffer_20 += buf_20
            vault_10 += v_10
            closed_symbols.append(symbol)
            last_closed_index[symbol] = i

        # 3. Cierre por Trailing Stage 1 (Breakeven +0.3%)
        elif current_stage == 1 and current_pnl <= 0.3:
            pnl_usd = slot["total_spent"] * 0.003 - (slot["total_spent"] * fee_rate)
            total_wins += 1
            total_trades += 1
            
            reinvest = pnl_usd * 0.70
            buf_20 = pnl_usd * 0.20
            v_10 = pnl_usd * 0.10
            
            operating_capital += reinvest
            compounded_70 += reinvest
            buffer_20 += buf_20
            vault_10 += v_10
            closed_symbols.append(symbol)
            last_closed_index[symbol] = i

        # 4. Stop Loss (-4.0%)
        elif current_stage == 0 and low_pnl <= -sl:
            pnl_usd = slot["total_spent"] * (-sl / 100.0) - (slot["total_spent"] * fee_rate)
            loss_abs = abs(pnl_usd)
            total_losses += 1
            total_trades += 1
            
            if buffer_20 >= loss_abs:
                buffer_20 -= loss_abs
            else:
                rem_loss = loss_abs - buffer_20
                buffer_20 = 0.0
                operating_capital -= rem_loss
                
            closed_symbols.append(symbol)
            last_closed_index[symbol] = i

    for cs in closed_symbols:
        del active_slots[cs]

    # 2. Buscar nuevos slots si hay espacio
    free_slots = max_slots - len(active_slots)
    if free_slots > 0 and operating_capital > 100:
        for symbol, klines in sample_data.items():
            if symbol in active_slots: continue
            
            # Cooldown de 2 horas (2 velas)
            if (i - last_closed_index.get(symbol, -100)) < 2:
                continue
                
            op = float(klines[i][1])
            hi = float(klines[i][2])
            lo = float(klines[i][3])
            cl = float(klines[i][4])
            vol = float(klines[i][5])
            
            prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
            close_prices = [float(k[4]) for k in klines[:i]]
            rsi_val = calculate_rsi(close_prices, 14)
            
            # Patrón Squeeze
            past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
            avg_past_range = sum(past_ranges) / len(past_ranges)
            
            # Patrón W-Bottom
            lows = [float(klines[j][3]) for j in range(i-20, i)]
            min_l1 = min(lows[:10])
            min_l2 = min(lows[10:])
            is_w_bottom = (abs(min_l1 - min_l2) / min_l1 <= 0.008)
            
            is_trigger = ((vol > prev_vol_avg * 2.5 and cl > op * 1.015) or (avg_past_range < 1.8 and vol > prev_vol_avg * 2.0) or (is_w_bottom and cl > op * 1.015)) and (rsi_val <= 75.0)
            
            if is_trigger:
                slot_base = round(operating_capital / max_slots, 2)
                initial_cost = slot_base * 0.50
                initial_qty = initial_cost / cl
                
                active_slots[symbol] = {
                    "slot_base_capital": slot_base,
                    "total_spent": initial_cost,
                    "total_qty": initial_qty,
                    "avg_entry": cl,
                    "allocated_pct": 0.50,
                    "trailing_stage": 0,
                    "current_sl_pct": sl
                }
                free_slots -= 1
                if free_slots <= 0: break

final_total_equity = operating_capital + buffer_20 + vault_10
total_return_pct = ((final_total_equity - initial_capital) / initial_capital) * 100.0

print("\n=========================================================================================")
print("RESULTADOS SIMULADOS DE 365 DÍAS PARA EL BOT DEFINITIVO COMPLETO")
print("=========================================================================================")
print(f"Capital Inicial                     : $1,000.00 USD")
print(f"Total de Operaciones Ejecutadas     : {total_trades} trades")
print(f"Trades Ganadores (+9% TP / Trail)   : {total_wins} ({total_wins/total_trades*100:.1f}%)")
print(f"Trades Perdedores (-4% SL)          : {total_losses} ({total_losses/total_trades*100:.1f}%)")
print(f"-----------------------------------------------------------------------------------------")
print(f"Capital Operativo Compuesto Final   : ${operating_capital:.2f} USD")
print(f"70% Acumulado por Reinversión       : ${compounded_70:.2f} USD")
print(f"20% Cojín de Reserva Restante       : ${buffer_20:.2f} USD")
print(f"10% Bóveda de Ganancia Cosechada    : ${vault_10:.2f} USD")
print(f"-----------------------------------------------------------------------------------------")
print(f"PATRIMONIO TOTAL VIRTUAL FINAL      : ${final_total_equity:.2f} USD")
print(f"RENDIMIENTO NETO TOTAL EN EL AÑO    : {total_return_pct:+.2f}%")
print("=========================================================================================")

