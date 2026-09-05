# evaluar_patrones_geometria.py - Estudio empírico de patrones geométricos (Squeeze, Donchian, W-Bottom) en Top 50-100
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== EVALUANDO PATRONES GEOMÉTRICOS Y DE ACCIÓN DE PRECIO EN TOP 50-100 ===")

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

# Evaluaremos 3 Patrones Geométricos en Python:
# 1. Volatility Squeeze Breakout (Compresión de rango previa + Ruptura de Volumen)
# 2. Donchian Channel Breakout (Ruptura del máximo de 24 horas)
# 3. W-Bottom (Doble Suelo Local en velas)

tp = 9.0
sl = 4.0

strategies = [
    {"name": "1. Compresión de Volatilidad (Squeeze + Breakout)", "type": "squeeze"},
    {"name": "2. Ruptura de Máximo de 24 Horas (Donchian Breakout)", "type": "donchian"},
    {"name": "3. Patrón Doble Suelo (W-Bottom Algorítmico)", "type": "w_bottom"}
]

print("\n=========================================================================================")
print("PATRÓN GEOMÉTRICO EVALUADO                        | TRADES | WINS | WIN RATE % | P&L NETO (USD)")
print("=========================================================================================")

for strat in strategies:
    total_trades = 0
    total_wins = 0
    total_losses = 0
    net_pnl_usd = 0.0
    st_type = strat["type"]
    
    for item in sample_data:
        klines = item["klines"]
        in_position = False
        avg_entry = 0.0
        allocated_pct = 0.0
        total_spent = 0.0
        total_qty = 0.0
        slot_capital = 100.0
        
        for i in range(30, len(klines)):
            op = float(klines[i][1])
            hi = float(klines[i][2])
            lo = float(klines[i][3])
            cl = float(klines[i][4])
            vol = float(klines[i][5])
            
            trigger = False
            
            if st_type == "squeeze":
                # Medir si las últimas 6 horas tuvieron un rango comprimido (< 1.8% promedio)
                past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
                avg_past_range = sum(past_ranges) / len(past_ranges)
                prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
                
                # Ruptura con volumen 2.5x desde compresión
                if avg_past_range < 2.0 and vol > prev_vol_avg * 2.5 and cl > op * 1.02:
                    trigger = True
                    
            elif st_type == "donchian":
                # Máximo de las últimas 24 horas
                max_24h = max(float(klines[j][2]) for j in range(i-24, i))
                prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
                
                # El precio supera el máximo de 24h con volumen
                if cl > max_24h and vol > prev_vol_avg * 2.0:
                    trigger = True
                    
            elif st_type == "w_bottom":
                # Buscar doble suelo local en los últimos 20 períodos
                lows = [float(klines[j][3]) for j in range(i-20, i)]
                min_l1 = min(lows[:10])
                min_l2 = min(lows[10:])
                
                # Suelos similares en nivel (+-0.8%) y vela actual superando la resistencia intermedia
                if abs(min_l1 - min_l2) / min_l1 <= 0.008 and cl > op * 1.015:
                    trigger = True

            if trigger and not in_position:
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
                
                if pnl_from_avg <= -1.2 and allocated_pct < 1.0:
                    cost = slot_capital * 0.10
                    qty = cost / current_price
                    total_spent += cost
                    total_qty += qty
                    avg_entry = total_spent / total_qty
                    allocated_pct += 0.10
                elif pnl_from_avg >= 2.0 and allocated_pct < 1.0 and pnl_from_avg < 7.0:
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
    print(f"{strat['name']:<50} | {total_trades:<6} | {total_wins:<4} | {win_rate:<10.1f}% | ${net_pnl_usd:<+10.2f}")

