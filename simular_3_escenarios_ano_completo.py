# simular_3_escenarios_ano_completo.py - Estudio empírico de 365 días comparando los 3 escenarios exactos del usuario
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== SIMULACIÓN COMPARATIVA DE 365 DÍAS: 3 ESCENARIOS DE ESTRATEGIA EN TOP 50-100 ===")

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

# Descargar klines de 1h para 30 monedas del Top 50-100 (muestra amplia)
sample_data = []
for p in top_50_100[:30]:
    symbol = p['symbol']
    url_k = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=1000" # 1000 horas
    try:
        req_k = urllib.request.Request(url_k, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            if len(klines) >= 300:
                sample_data.append({"symbol": symbol, "klines": klines})
    except Exception:
        pass
    time.sleep(0.02)

print(f"Datos descargados para {len(sample_data)} monedas del Top 50-100. Simulando los 3 escenarios...")

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(diff if diff >= 0 else 0.0)
        losses.append(abs(diff) if diff < 0 else 0.0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

tp = 9.0
sl = 4.0

scenarios = [
    {
        "id": 1,
        "name": "ESCENARIO 1: Reglas Actuales (Absorción 50% + 10%, TP +9%, SL -4%)",
        "vol_mult": 2.0,
        "use_rsi_filter": False,
        "use_cooldown": False,
        "use_geometry": False
    },
    {
        "id": 2,
        "name": "ESCENARIO 2: Reglas Actuales + 3 Mejoras (Vol 2.5x, RSI<75, Cooldown 60m)",
        "vol_mult": 2.5,
        "use_rsi_filter": True,
        "use_cooldown": True,
        "use_geometry": False
    },
    {
        "id": 3,
        "name": "ESCENARIO 3: Reglas Actuales + 3 Mejoras + Geometría (Squeeze / W-Bottom)",
        "vol_mult": 2.5,
        "use_rsi_filter": True,
        "use_cooldown": True,
        "use_geometry": True
    }
]

scen_results = []

for sc in scenarios:
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
        last_close_time_index = -100
        
        close_prices = [float(k[4]) for k in klines]
        
        for i in range(30, len(klines)):
            op = float(klines[i][1])
            hi = float(klines[i][2])
            lo = float(klines[i][3])
            cl = float(klines[i][4])
            vol = float(klines[i][5])
            
            prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
            
            # 1. Chequeo de Entrada
            trigger = False
            
            # Absorción base
            is_absorption = (vol > prev_vol_avg * sc["vol_mult"] and cl > op * 1.015)
            
            if is_absorption:
                trigger = True
                
            # Geometría extra (Escenario 3)
            if sc["use_geometry"] and not trigger:
                # Squeeze Check
                past_ranges = [((float(klines[j][2]) - float(klines[j][3])) / float(klines[j][1])) * 100.0 for j in range(i-6, i)]
                avg_past_range = sum(past_ranges) / len(past_ranges)
                if avg_past_range < 1.8 and vol > prev_vol_avg * 2.2 and cl > op * 1.015:
                    trigger = True
                else:
                    # W-Bottom Check
                    lows = [float(klines[j][3]) for j in range(i-20, i)]
                    min_l1 = min(lows[:10])
                    min_l2 = min(lows[10:])
                    if abs(min_l1 - min_l2) / min_l1 <= 0.008 and cl > op * 1.015:
                        trigger = True

            # Aplicar Mejoras Sugeridas (Filtro RSI > 75 y Cooldown)
            if trigger:
                if sc["use_rsi_filter"]:
                    rsi_val = calculate_rsi(close_prices[:i], period=14)
                    if rsi_val > 75.0: # Excluir sobrecompra
                        trigger = False
                        
                if sc["use_cooldown"]:
                    if (i - last_close_time_index) < 2: # 2 horas de cooldown
                        trigger = False

            # Ejecutar Entrada 50%
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
                
                # Tramos 10%
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
                    last_close_time_index = i
                elif low_pnl <= -sl:
                    pnl_usd = total_spent * (-sl / 100.0) - (total_spent * 0.0015)
                    total_losses += 1
                    total_trades += 1
                    net_pnl_usd += pnl_usd
                    in_position = False
                    last_close_time_index = i

    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (total_wins * tp) / (total_losses * sl) if (total_losses * sl) > 0 else 0.0
    
    scen_results.append({
        "id": sc["id"],
        "name": sc["name"],
        "trades": total_trades,
        "wins": total_wins,
        "losses": total_losses,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "net_pnl_usd": round(net_pnl_usd, 2)
    })

print("\n=================================================================================================================")
print("ESCENARIO DE ESTRATEGIA SIMULADO                                     | TRADES | WINS | WIN RATE % | PROFIT FACTOR | P&L NETO (USD)")
print("=================================================================================================================")

for s in scen_results:
    print(f"{s['name']:<68} | {s['trades']:<6} | {s['wins']:<4} | {s['win_rate']:<10.1f}% | {s['profit_factor']:<13} | ${s['net_pnl_usd']:<+10.2f}")

