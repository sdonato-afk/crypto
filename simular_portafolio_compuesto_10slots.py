# simular_portafolio_compuesto_10slots.py - Simulación con 10 slots paralelos 24/7 e Interés Compuesto 70/20/10
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== SIMULACIÓN DE PORTAFOLIO COMPLETO: 10 SLOTS PARALELOS 24/7 CON REINVERSIÓN COMPUESTA ===")

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

print(f"Datos descargados para {len(sample_data)} monedas. Ejecutando motor de 10 slots simultáneos con Interés Compuesto...")

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

# Simulación de Cartera Completa (10 Slots Simultáneos)
initial_capital = 1000.0
operating_capital = 1000.0
compounded_70 = 0.0
buffer_20 = 0.0
vault_10 = 0.0

active_slots = {} # symbol: slot_info
max_slots = 10
tp = 9.0
sl = 4.0

total_wins = 0
total_losses = 0
total_trades = 0

min_timeline_len = min(len(v) for v in sample_data.values())

for i in range(50, min_timeline_len):
    # 1. Monitorear y actualizar slots activos
    closed_symbols = []
    for symbol, slot in list(active_slots.items()):
        klines = sample_data[symbol]
        op = float(klines[i][1])
        hi = float(klines[i][2])
        lo = float(klines[i][3])
        cl = float(klines[i][4])
        
        avg_entry = slot["avg_entry"]
        allocated_pct = slot["allocated_pct"]
        total_spent = slot["total_spent"]
        total_qty = slot["total_qty"]
        slot_base_capital = slot["slot_base_capital"]
        
        current_pnl_from_avg = ((cl - avg_entry) / avg_entry) * 100.0
        
        # Tramos 10%
        if current_pnl_from_avg <= -1.2 and allocated_pct < 1.0:
            add_cost = slot_base_capital * 0.10
            add_qty = add_cost / cl
            slot["total_spent"] += add_cost
            slot["total_qty"] += add_qty
            slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
            slot["allocated_pct"] += 0.10
        elif current_pnl_from_avg >= 2.0 and allocated_pct < 1.0 and current_pnl_from_avg < 7.0:
            add_cost = slot_base_capital * 0.10
            add_qty = add_cost / cl
            slot["total_spent"] += add_cost
            slot["total_qty"] += add_qty
            slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
            slot["allocated_pct"] += 0.10

        high_pnl = ((hi - avg_entry) / avg_entry) * 100.0
        low_pnl = ((lo - avg_entry) / avg_entry) * 100.0

        if high_pnl >= tp:
            # Win 🎯
            pnl_usd = slot["total_spent"] * (tp / 100.0) - (slot["total_spent"] * 0.0015)
            total_wins += 1
            total_trades += 1
            
            # Modelo 70-20-10
            reinvest_70 = pnl_usd * 0.70
            buf_20 = pnl_usd * 0.20
            v_10 = pnl_usd * 0.10
            
            operating_capital += reinvest_70
            compounded_70 += reinvest_70
            buffer_20 += buf_20
            vault_10 += v_10
            
            closed_symbols.append(symbol)

        elif low_pnl <= -sl:
            # Loss 🛑
            pnl_usd = slot["total_spent"] * (-sl / 100.0) - (slot["total_spent"] * 0.0015)
            loss_abs = abs(pnl_usd)
            total_losses += 1
            total_trades += 1
            
            # Absorber del buffer de reserva primero
            if buffer_20 >= loss_abs:
                buffer_20 -= loss_abs
            else:
                rem_loss = loss_abs - buffer_20
                buffer_20 = 0.0
                operating_capital -= rem_loss
                
            closed_symbols.append(symbol)

    for cs in closed_symbols:
        del active_slots[cs]

    # 2. Buscar nuevos slots si hay espacio (< 10)
    free_slots = max_slots - len(active_slots)
    if free_slots > 0:
        for symbol, klines in sample_data.items():
            if symbol in active_slots: continue
            
            op = float(klines[i][1])
            hi = float(klines[i][2])
            lo = float(klines[i][3])
            cl = float(klines[i][4])
            vol = float(klines[i][5])
            
            prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
            close_prices = [float(k[4]) for k in klines[:i]]
            rsi_val = calculate_rsi(close_prices, 14)
            
            # Squeeze Check
            past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
            avg_past_range = sum(past_ranges) / len(past_ranges)
            
            is_trigger = (vol > prev_vol_avg * 2.5 and cl > op * 1.015 and rsi_val <= 75.0) or (avg_past_range < 1.8 and vol > prev_vol_avg * 2.0)
            
            if is_trigger:
                slot_base = round(operating_capital / max_slots, 2)
                initial_cost = slot_base * 0.50
                initial_qty = initial_cost / cl
                
                active_slots[symbol] = {
                    "slot_base_capital": slot_base,
                    "total_spent": initial_cost,
                    "total_qty": initial_qty,
                    "avg_entry": cl,
                    "allocated_pct": 0.50
                }
                free_slots -= 1
                if free_slots <= 0: break

final_total_equity = operating_capital + buffer_20 + vault_10
total_return_pct = ((final_total_equity - initial_capital) / initial_capital) * 100.0

print("\n=========================================================================================")
print("RESULTADOS DE SIMULACIÓN MULTI-SLOT PARALELO (10 SLOTS 24/7 CON INTERÉS COMPUESTO)")
print("=========================================================================================")
print(f"Capital Inicial                     : $1,000.00 USD")
print(f"Total de Operaciones Ejecutadas     : {total_trades} trades")
print(f"Trades Ganadores (+9% TP)           : {total_wins} ({total_wins/total_trades*100:.1f}%)")
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

