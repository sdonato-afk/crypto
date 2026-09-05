# simular_estrategia_50_100.py - Simulación cuantitativa de la estrategia 50-100 con Escalonamiento (DCA + Piramidación)
import urllib.request
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== SIMULACIÓN ESTRATÉGICA: TOP 50-100 CON ESCALONAMIENTO 50% + 10% (TP +9% / SL -3%) ===")

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

# Tomar del ranking 50 al 100
top_50_100 = usdt_pairs[50:100]

print(f"Pares del Top 50-100 seleccionados: {len(top_50_100)} monedas.")

# Simulación de rendimiento histórico
stats = {
    "total_trades": 0,
    "wins_9pct": 0,
    "losses_3pct": 0,
    "avg_legs_used": [],
    "total_pnl_usd": 0.0
}

for p in top_50_100[:20]: # Muestra representativa de 20 monedas del Top 50-100
    symbol = p['symbol']
    url_k = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=500" # 500 horas (~20 días)
    try:
        req_k = urllib.request.Request(url_k, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            
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
                
                # Calcular promedio de volumen previo (20 horas)
                prev_vol_avg = sum(float(klines[j][5]) for j in range(i-20, i)) / 20.0
                
                # Señal de entrada: volumen 2.2x y mecha o vela verde +2%
                if not in_position and vol > prev_vol_avg * 2.2 and cl > op * 1.015:
                    in_position = True
                    # Entrada inicial 50% ($50)
                    allocated_pct = 0.50
                    cost = slot_capital * 0.50
                    qty = cost / cl
                    total_spent = cost
                    total_qty = qty
                    avg_entry = total_spent / total_qty
                    legs_count = 1
                    
                elif in_position:
                    # Monitorear si se dispara compras adicionales del 10% ($10)
                    # Caso A: Caída de -1.2% respecto al precio promedio -> Mejorar entrada (DCA)
                    current_price = cl
                    pnl_from_avg = ((current_price - avg_entry) / avg_entry) * 100.0
                    
                    if pnl_from_avg <= -1.2 and allocated_pct < 1.0:
                        add_pct = 0.10
                        cost = slot_capital * add_pct
                        qty = cost / current_price
                        total_spent += cost
                        total_qty += qty
                        avg_entry = total_spent / total_qty
                        allocated_pct += add_pct
                        legs_count += 1
                        
                    # Caso B: Subida de +2.0% respecto al precio promedio -> Piramidar a la alza
                    elif pnl_from_avg >= 2.0 and allocated_pct < 1.0 and pnl_from_avg < 6.0:
                        add_pct = 0.10
                        cost = slot_capital * add_pct
                        qty = cost / current_price
                        total_spent += cost
                        total_qty += qty
                        avg_entry = total_spent / total_qty
                        allocated_pct += add_pct
                        legs_count += 1

                    # Evaluar Cierre: TP +9% o SL -3% desde el precio promedio ponderado
                    high_pnl = ((hi - avg_entry) / avg_entry) * 100.0
                    low_pnl = ((lo - avg_entry) / avg_entry) * 100.0
                    
                    if high_pnl >= 9.0:
                        # Take Profit alcanzado
                        pnl_usd = total_spent * 0.09 - (total_spent * 0.0015) # comisiones
                        stats["wins_9pct"] += 1
                        stats["total_trades"] += 1
                        stats["total_pnl_usd"] += pnl_usd
                        stats["avg_legs_used"].append(legs_count)
                        in_position = False
                    elif low_pnl <= -3.0:
                        # Stop Loss alcanzado
                        pnl_usd = total_spent * (-0.03) - (total_spent * 0.0015)
                        stats["losses_3pct"] += 1
                        stats["total_trades"] += 1
                        stats["total_pnl_usd"] += pnl_usd
                        stats["avg_legs_used"].append(legs_count)
                        in_position = False

    except Exception:
        pass
    time.sleep(0.03)

print("\n--- RESULTADOS DE LA SIMULACIÓN DE ESCALONAMIENTO EN TOP 50-100 ---")
tot = stats["total_trades"]
if tot > 0:
    win_rate = (stats["wins_9pct"] / tot) * 100.0
    avg_legs = sum(stats["avg_legs_used"]) / len(stats["avg_legs_used"]) if stats["avg_legs_used"] else 1
    print(f"Total de Trades Ejecutados: {tot}")
    print(f"Victorias (+9% TP): {stats['wins_9pct']} ({win_rate:.1f}%)")
    print(f"Derrotas (-3% SL): {stats['losses_3pct']} ({100.0 - win_rate:.1f}%)")
    print(f"Promedio de Entradas (Legs) por Trade: {avg_legs:.2f} patas de compra (de 1 a 6)")
    print(f"P&L Neto Acumulado Simulado: ${stats['total_pnl_usd']:+.2f} USD")
else:
    print("No se registraron trades en el período muestreado.")

