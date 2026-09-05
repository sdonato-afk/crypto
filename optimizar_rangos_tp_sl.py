# optimizar_rangos_tp_sl.py - Grid Search de optimización cuantitativa para TP y SL en Top 50-100
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== OPTIMIZACIÓN CUANTITATIVA DE RANGOS TP / SL PARA TOP 50-100 EN BINANCE ===")

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

# Descargar klines de muestra para 25 monedas del Top 50-100
sample_data = []
for p in top_50_100[:25]:
    symbol = p['symbol']
    url_k = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=500"
    try:
        req_k = urllib.request.Request(url_k, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            if len(klines) >= 200:
                sample_data.append({"symbol": symbol, "klines": klines})
    except Exception:
        pass
    time.sleep(0.02)

print(f"Datos descargados para {len(sample_data)} monedas. Evaluando combinaciones de TP y SL...")

tp_options = [6.0, 7.5, 9.0, 10.5, 12.0]
sl_options = [2.0, 2.5, 3.0, 3.5, 4.0]

grid_results = []

for tp in tp_options:
    for sl in sl_options:
        total_trades = 0
        total_wins = 0
        total_losses = 0
        net_pnl_usd = 0.0
        
        for item in sample_data:
            klines = item["klines"]
            in_position = False
            avg_entry = 0.0
            allocated_pct = 0.0
            total_spent = 0.0
            total_qty = 0.0
            slot_capital = 100.0
            
            for i in range(20, len(klines)):
                op = float(klines[i][1])
                hi = float(klines[i][2])
                lo = float(klines[i][3])
                cl = float(klines[i][4])
                vol = float(klines[i][5])
                
                prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
                
                if not in_position and vol > prev_vol_avg * 2.2 and cl > op * 1.015:
                    in_position = True
                    allocated_pct = 0.50
                    cost = slot_capital * 0.50
                    qty = cost / cl
                    total_spent = cost
                    total_qty = qty
                    avg_entry = total_spent / total_qty
                    
                elif in_position:
                    current_price = cl
                    pnl_from_avg = ((current_price - avg_entry) / avg_entry) * 100.0
                    
                    # Carga tramos 10%
                    if pnl_from_avg <= -1.2 and allocated_pct < 1.0:
                        cost = slot_capital * 0.10
                        qty = cost / current_price
                        total_spent += cost
                        total_qty += qty
                        avg_entry = total_spent / total_qty
                        allocated_pct += 0.10
                    elif pnl_from_avg >= 2.0 and allocated_pct < 1.0 and pnl_from_avg < (tp - 2.0):
                        cost = slot_capital * 0.10
                        qty = cost / current_price
                        total_spent += cost
                        total_qty += qty
                        avg_entry = total_spent / total_qty
                        allocated_pct += 0.10
                    
                    high_pnl = ((hi - avg_entry) / avg_entry) * 100.0
                    low_pnl = ((lo - avg_entry) / avg_entry) * 100.0
                    
                    if high_pnl >= tp:
                        pnl_usd = total_spent * (tp / 100.0) - (total_spent * 0.0015)
                        total_wins += 1
                        total_trades += 1
                        net_pnl_usd += pnl_usd
                        in_position = False
                    elif low_pnl <= -sl:
                        pnl_usd = total_spent * (-sl / 100.0) - (total_spent * 0.0015)
                        total_losses += 1
                        total_trades += 1
                        net_pnl_usd += pnl_usd
                        in_position = False

        win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
        profit_factor = (total_wins * tp) / (total_losses * sl) if (total_losses * sl) > 0 else 0.0
        
        grid_results.append({
            "tp": tp,
            "sl": sl,
            "rr_ratio": round(tp / sl, 2),
            "trades": total_trades,
            "win_rate": round(win_rate, 1),
            "net_pnl_usd": round(net_pnl_usd, 2),
            "profit_factor": round(profit_factor, 2)
        })

grid_results.sort(key=lambda x: x['net_pnl_usd'], reverse=True)

print("\n=========================================================================================")
print("TP %   | SL %   | RATIO R:R | TRADES | WIN RATE % | PROFIT FACTOR | P&L NETO SIMULADO (USD)")
print("=========================================================================================")

for g in grid_results:
    print(f"{g['tp']:<6}% | {g['sl']:<6}% | {g['rr_ratio']:<9} | {g['trades']:<6} | {g['win_rate']:<10}% | {g['profit_factor']:<13} | ${g['net_pnl_usd']:<+10.2f}")

