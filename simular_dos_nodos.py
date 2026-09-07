import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== INICIANDO SIMULACIÓN DE 2 NODOS (365 DÍAS) ===")

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

top_1_50 = usdt_pairs[0:50]
top_51_100 = usdt_pairs[50:100]

def download_data(pairs, max_coins=35):
    sample = {}
    for p in pairs[:max_coins]:
        symbol = p['symbol']
        url_k = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=1000"
        try:
            req_k = urllib.request.Request(url_k, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_k, timeout=5) as resp:
                klines = json.loads(resp.read().decode('utf-8'))
                if len(klines) >= 500:
                    sample[symbol] = klines
        except Exception:
            pass
        time.sleep(0.02)
    return sample

print("Descargando datos Nodo A (Top 1-50)...")
data_node_a = download_data(top_1_50)
print("Descargando datos Nodo B (Top 51-100)...")
data_node_b = download_data(top_51_100)

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

def simulate_node(sample_data, params):
    initial_capital = 1000.0
    operating_capital = 1000.0
    compounded_70 = 0.0
    buffer_20 = 0.0
    vault_10 = 0.0

    active_slots = {}
    max_slots = 10
    fee_rate = 0.00024
    
    tp = params['tp']
    sl = params['sl']
    t1_trig = params['t1_trig']
    t1_lock = params['t1_lock']
    t2_trig = params['t2_trig']
    t2_lock = params['t2_lock']

    total_wins = 0
    wins_tp = 0
    wins_trail2 = 0
    wins_trail1 = 0
    total_losses = 0
    total_trades = 0
    last_closed_index = {}

    if not sample_data: return None
    min_timeline_len = min(len(v) for v in sample_data.values())

    for i in range(50, min_timeline_len):
        closed_symbols = []
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
            
            current_pnl = ((cl - avg_entry) / avg_entry) * 100.0
            
            # Scale In
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

            # Update trailing
            if high_pnl >= t1_trig and trailing_stage < 1:
                slot["trailing_stage"] = 1
            if high_pnl >= t2_trig and trailing_stage < 2:
                slot["trailing_stage"] = 2

            current_stage = slot.get("trailing_stage", 0)

            closed_with_profit = 0
            closed_with_loss = 0
            close_cause = ""

            if high_pnl >= tp:
                pnl_usd = slot["total_spent"] * (tp / 100.0) - (slot["total_spent"] * fee_rate)
                closed_with_profit = pnl_usd
                wins_tp += 1
                close_cause = "tp"
            elif current_stage == 2 and current_pnl <= t2_lock:
                pnl_usd = slot["total_spent"] * (t2_lock / 100.0) - (slot["total_spent"] * fee_rate)
                closed_with_profit = pnl_usd
                wins_trail2 += 1
                close_cause = "t2"
            elif current_stage == 1 and current_pnl <= t1_lock:
                pnl_usd = slot["total_spent"] * (t1_lock / 100.0) - (slot["total_spent"] * fee_rate)
                closed_with_profit = pnl_usd
                wins_trail1 += 1
                close_cause = "t1"
            elif current_stage == 0 and low_pnl <= -sl:
                pnl_usd = slot["total_spent"] * (-sl / 100.0) - (slot["total_spent"] * fee_rate)
                closed_with_loss = abs(pnl_usd)
                close_cause = "sl"
                
            if close_cause:
                if closed_with_profit > 0:
                    total_wins += 1
                    total_trades += 1
                    reinvest = closed_with_profit * 0.70
                    buf_20 = closed_with_profit * 0.20
                    v_10 = closed_with_profit * 0.10
                    operating_capital += reinvest
                    compounded_70 += reinvest
                    buffer_20 += buf_20
                    vault_10 += v_10
                elif closed_with_loss > 0:
                    total_losses += 1
                    total_trades += 1
                    if buffer_20 >= closed_with_loss:
                        buffer_20 -= closed_with_loss
                    else:
                        rem = closed_with_loss - buffer_20
                        buffer_20 = 0.0
                        operating_capital -= rem
                
                closed_symbols.append(symbol)
                last_closed_index[symbol] = i

        for cs in closed_symbols:
            del active_slots[cs]

        free_slots = max_slots - len(active_slots)
        if free_slots > 0 and operating_capital > 100:
            for symbol, klines in sample_data.items():
                if symbol in active_slots: continue
                if (i - last_closed_index.get(symbol, -100)) < 2: continue
                
                op = float(klines[i][1])
                cl = float(klines[i][4])
                vol = float(klines[i][5])
                
                prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
                close_prices = [float(k[4]) for k in klines[:i]]
                rsi_val = calculate_rsi(close_prices, 14)
                
                past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
                avg_past_range = sum(past_ranges) / len(past_ranges)
                
                lows = [float(klines[j][3]) for j in range(i-20, i)]
                min_l1 = min(lows[:10])
                min_l2 = min(lows[10:])
                is_w_bottom = (abs(min_l1 - min_l2) / min_l1 <= 0.008)
                
                is_trigger = ((vol > prev_vol_avg * 2.5 and cl > op * 1.015) or (avg_past_range < 1.8 and vol > prev_vol_avg * 2.0) or (is_w_bottom and cl > op * 1.015)) and (rsi_val <= 75.0)
                
                if is_trigger:
                    slot_base = round(operating_capital / max_slots, 2)
                    active_slots[symbol] = {
                        "slot_base_capital": slot_base,
                        "total_spent": slot_base * 0.50,
                        "total_qty": (slot_base * 0.50) / cl,
                        "avg_entry": cl,
                        "allocated_pct": 0.50,
                        "trailing_stage": 0
                    }
                    free_slots -= 1
                    if free_slots <= 0: break

    final_total_equity = operating_capital + buffer_20 + vault_10
    total_return_pct = ((final_total_equity - initial_capital) / initial_capital) * 100.0

    return {
        "trades": total_trades,
        "wins": total_wins,
        "losses": total_losses,
        "tp": wins_tp,
        "t2": wins_trail2,
        "t1": wins_trail1,
        "return_pct": total_return_pct,
        "equity": final_total_equity,
        "vault": vault_10,
        "operating": operating_capital
    }

params_a = {
    'tp': 9.0, 'sl': 4.0, 't1_trig': 4.0, 't1_lock': 0.3, 't2_trig': 6.5, 't2_lock': 4.0
}
params_b = {
    'tp': 12.0, 'sl': 7.0, 't1_trig': 6.0, 't1_lock': 0.5, 't2_trig': 9.0, 't2_lock': 5.0
}

print("\n--- Ejecutando Simulación Nodo A ---")
res_a = simulate_node(data_node_a, params_a)

print("--- Ejecutando Simulación Nodo B ---")
res_b = simulate_node(data_node_b, params_b)

def pct_format(val, total):
    if total == 0: return "0.0%"
    return f"{(val/total)*100:.1f}%"

print("\n=========================================================================================")
print("                      RESULTADOS DE LA ARQUITECTURA DE DOS NODOS (365 DÍAS)              ")
print("=========================================================================================")
print(f"                       NODO A (TOP 1-50)            NODO B (TOP 51-100)       ")
print(f"Parámetros Clave     : SL -4% / TP +9%              SL -7% / TP +12%")
print(f"Trailing Stages      : BE +0.3% / Lock +4%          BE +0.5% / Lock +5%")
print("-----------------------------------------------------------------------------------------")
print(f"Capital Inicial      : $1,000.00                    $1,000.00")
print(f"Trades Totales       : {res_a['trades']:<28} {res_b['trades']}")
print(f"Tasa de Acierto      : {pct_format(res_a['wins'], res_a['trades']):<28} {pct_format(res_b['wins'], res_b['trades'])}")
print(f"Victorias (Total)    : {res_a['wins']:<28} {res_b['wins']}")
print(f"  - Por TP Puro      : {res_a['tp']:<28} {res_b['tp']}")
print(f"  - Por Trail Lock   : {res_a['t2']:<28} {res_b['t2']}")
print(f"  - Por Breakeven    : {res_a['t1']:<28} {res_b['t1']}")
print(f"Stop Losses          : {res_a['losses']:<28} {res_b['losses']}")
print("-----------------------------------------------------------------------------------------")
print(f"Capital Operativo    : ${res_a['operating']:<27.2f} ${res_b['operating']:.2f}")
print(f"Bóveda Cosechada     : ${res_a['vault']:<27.2f} ${res_b['vault']:.2f}")
print(f"PATRIMONIO TOTAL     : ${res_a['equity']:<27.2f} ${res_b['equity']:.2f}")
print(f"RENDIMIENTO ANUAL    : {res_a['return_pct']:<+28.2f}% {res_b['return_pct']:+.2f}%")
print("=========================================================================================")
total_portfolio = res_a['equity'] + res_b['equity']
total_yield = ((total_portfolio - 2000.0) / 2000.0) * 100.0
print(f"RENDIMIENTO DEL PORTAFOLIO GLOBAL CONSOLIDADO (Base $2,000): {total_yield:+.2f}%")
print("=========================================================================================")
