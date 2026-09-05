# simular_palanca_y_reinversion.py - Estudio empírico de potenciamiento de renta (Reinversión 100% + Palanca 2x)
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== POTENCIACIÓN DE RENTA: REINVERSIÓN 100% Y PALANCA BARRERA 2X SPOT ===")

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

min_timeline_len = min(len(v) for v in sample_data.values())

def run_portfolio_simulation(reinvest_ratio=0.70, leverage=1.0):
    initial_capital = 1000.0
    operating_capital = 1000.0
    compounded_profit = 0.0
    vault_profit = 0.0
    
    active_slots = {}
    max_slots = 10
    tp = 9.0
    sl = 4.0
    total_wins = 0
    total_losses = 0
    
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
            
            current_pnl_from_avg = ((cl - avg_entry) / avg_entry) * 100.0
            
            if current_pnl_from_avg <= -1.2 and allocated_pct < 1.0:
                add_cost = slot_base_capital * 0.10
                slot["total_spent"] += add_cost
                slot["total_qty"] += (add_cost / cl)
                slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
                slot["allocated_pct"] += 0.10
            elif current_pnl_from_avg >= 2.0 and allocated_pct < 1.0 and current_pnl_from_avg < 7.0:
                add_cost = slot_base_capital * 0.10
                slot["total_spent"] += add_cost
                slot["total_qty"] += (add_cost / cl)
                slot["avg_entry"] = slot["total_spent"] / slot["total_qty"]
                slot["allocated_pct"] += 0.10

            high_pnl = ((hi - avg_entry) / avg_entry) * 100.0 * leverage
            low_pnl = ((lo - avg_entry) / avg_entry) * 100.0 * leverage

            if high_pnl >= (tp * leverage):
                pnl_usd = (slot["total_spent"] * leverage) * (tp / 100.0) - (slot["total_spent"] * 0.0015 * leverage)
                total_wins += 1
                
                reinvest = pnl_usd * reinvest_ratio
                vault = pnl_usd * (1.0 - reinvest_ratio)
                
                operating_capital += reinvest
                compounded_profit += reinvest
                vault_profit += vault
                closed_symbols.append(symbol)

            elif low_pnl <= (-sl * leverage):
                pnl_usd = (slot["total_spent"] * leverage) * (-sl / 100.0) - (slot["total_spent"] * 0.0015 * leverage)
                total_losses += 1
                operating_capital += pnl_usd # restar pérdida
                closed_symbols.append(symbol)

        for cs in closed_symbols:
            del active_slots[cs]

        free_slots = max_slots - len(active_slots)
        if free_slots > 0 and operating_capital > 100:
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
                
                past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
                avg_past_range = sum(past_ranges) / len(past_ranges)
                
                is_trigger = (vol > prev_vol_avg * 2.5 and cl > op * 1.015 and rsi_val <= 75.0) or (avg_past_range < 1.8 and vol > prev_vol_avg * 2.0)
                
                if is_trigger:
                    slot_base = round(operating_capital / max_slots, 2)
                    initial_cost = slot_base * 0.50
                    active_slots[symbol] = {
                        "slot_base_capital": slot_base,
                        "total_spent": initial_cost,
                        "total_qty": initial_cost / cl,
                        "avg_entry": cl,
                        "allocated_pct": 0.50
                    }
                    free_slots -= 1
                    if free_slots <= 0: break

    total_equity = operating_capital + vault_profit
    net_return_pct = ((total_equity - initial_capital) / initial_capital) * 100.0
    return round(total_equity, 2), round(net_return_pct, 2), total_wins, total_losses

print("\n=========================================================================================")
print("MODO DE POTENCIACIÓN EVALUADO             | EQUIDAD FINAL | WIN RATE % | RENDIMIENTO NETO %")
print("=========================================================================================")

eq1, ret1, w1, l1 = run_portfolio_simulation(reinvest_ratio=0.70, leverage=1.0)
print(f"1. Actual (Spot 1x / Reinversión 70%)     | ${eq1:<12} | {(w1/(w1+l1))*100:<10.1f}% | {ret1:+.2f}%")

eq2, ret2, w2, l2 = run_portfolio_simulation(reinvest_ratio=1.00, leverage=1.0)
print(f"2. Reinversión 100% Completa (Spot 1x)     | ${eq2:<12} | {(w2/(w2+l2))*100:<10.1f}% | {ret2:+.2f}%")

eq3, ret3, w3, l3 = run_portfolio_simulation(reinvest_ratio=1.00, leverage=2.0)
print(f"3. SUPER-CARGADO (Spot Margin 2x + 100%)  | ${eq3:<12} | {(w3/(w3+l3))*100:<10.1f}% | {ret3:+.2f}%")

