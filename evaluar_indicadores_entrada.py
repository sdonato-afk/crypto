# evaluar_indicadores_entrada.py - Simulación de nuevos filtros técnicos (RSI + EMA + Confirmación) para aumentar Win Rate
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== EVALUANDO NUEVOS INDICADORES DE ENTRADA (RSI + EMA + CONFIRMACIÓN VELA) ===")

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

def calculate_ema(prices, period=50):
    if len(prices) < period:
        return prices[-1]
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

# Test 1: Baseline actual (Absorción sin filtros extra)
# Test 2: Absorción + Filtro EMA 50 (Precio > EMA 50)
# Test 3: Absorción + Filtro RSI (RSI 14 entre 35 y 60)
# Test 4: Absorción + Vela de Confirmación Verde (c_close > c_open)

tests = [
    {"name": "1. Baseline (Solo Absorción actual)", "use_ema": False, "use_rsi": False, "use_green_confirm": False},
    {"name": "2. Absorción + Filtro de Tendencia (Precio > EMA 50)", "use_ema": True, "use_rsi": False, "use_green_confirm": False},
    {"name": "3. Absorción + Filtro RSI Saludable (RSI 35-60)", "use_ema": False, "use_rsi": True, "use_green_confirm": False},
    {"name": "4. Absorción + Confirmación de Vela Verde", "use_ema": False, "use_rsi": False, "use_green_confirm": True},
    {"name": "5. COMBO COMPLETO (Absorción + EMA 50 + RSI + Vela Verde)", "use_ema": True, "use_rsi": True, "use_green_confirm": True}
]

tp = 9.0
sl = 4.0

print("\n=========================================================================================")
print("CONFIGURACIÓN DE ENTRADA                          | TRADES | WINS | WIN RATE % | P&L NETO (USD)")
print("=========================================================================================")

for t in tests:
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
        
        close_prices = [float(k[4]) for k in klines]
        
        for i in range(50, len(klines)):
            op = float(klines[i][1])
            hi = float(klines[i][2])
            lo = float(klines[i][3])
            cl = float(klines[i][4])
            vol = float(klines[i][5])
            
            prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
            
            # Condiciones base de absorción
            base_signal = (vol > prev_vol_avg * 2.2 and cl > op * 1.01)
            
            if base_signal:
                # Aplicar filtros adicionales
                if t["use_ema"]:
                    ema50 = calculate_ema(close_prices[:i], period=50)
                    if cl < ema50: # Si está por debajo de la tendencia de 50 periodos, descartar
                        continue
                        
                if t["use_rsi"]:
                    rsi14 = calculate_rsi(close_prices[:i], period=14)
                    if rsi14 > 62.0 or rsi14 < 32.0: # Evitar sobrecomprados o caída libre
                        continue
                        
                if t["use_green_confirm"]:
                    if cl <= op: # Exigir cierre verde
                        continue

                if not in_position:
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
    print(f"{t['name']:<50} | {total_trades:<6} | {total_wins:<4} | {win_rate:<10.1f}% | ${net_pnl_usd:<+10.2f}")

