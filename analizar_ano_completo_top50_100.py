# analizar_ano_completo_top50_100.py - Estudio empírico de 365 días en Binance (Top 50-100)
import urllib.request
import json
import time
import sys
import statistics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== INICIANDO ESTUDIO DE 365 DÍAS (ÚLTIMO AÑO) PARA TOP 50-100 EN BINANCE ===")

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
print(f"Pares del Top 50 al 100 seleccionados ({len(top_50_100)} monedas). Solicitando 365 velas diarias a Binance...")

results = []

for idx, p in enumerate(top_50_100):
    symbol = p['symbol']
    # 365 velas diarias
    url_klines = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=365"
    try:
        req_k = urllib.request.Request(url_klines, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            
            if len(klines) < 90:
                continue

            spikes_9pct_high = 0 # Días donde la mecha máxima (High vs Open) superó +9.0%
            spikes_9pct_close = 0 # Días donde la vela CERRÓ en verde con >= +9.0%
            daily_ranges = []

            for k in klines:
                op = float(k[1])
                hi = float(k[2])
                lo = float(k[3])
                cl = float(k[4])
                
                if op > 0:
                    day_range = ((hi - lo) / op) * 100.0
                    daily_ranges.append(day_range)
                    
                    high_wick_pct = ((hi - op) / op) * 100.0
                    close_ret_pct = ((cl - op) / op) * 100.0
                    
                    if high_wick_pct >= 9.0:
                        spikes_9pct_high += 1
                    if close_ret_pct >= 9.0:
                        spikes_9pct_close += 1

            total_days = len(klines)
            prob_high_9 = (spikes_9pct_high / total_days) * 100.0
            prob_close_9 = (spikes_9pct_close / total_days) * 100.0
            avg_range = sum(daily_ranges) / len(daily_ranges)

            results.append({
                "symbol": symbol,
                "rank": idx + 51,
                "volume_24h_m": float(p['quoteVolume']) / 1_000_000,
                "avg_range_pct": round(avg_range, 2),
                "spikes_high_9": spikes_9pct_high,
                "spikes_close_9": spikes_9pct_close,
                "total_days": total_days,
                "prob_high_9_pct": round(prob_high_9, 1),
                "prob_close_9_pct": round(prob_close_9, 1)
            })
            
    except Exception as e:
        pass
    time.sleep(0.04)

# Ordenar por probabilidad de tocar +9% intradiario (High)
results.sort(key=lambda x: x['prob_high_9_pct'], reverse=True)

print("\n=========================================================================================")
print("RANK | TICKER       | RANGO DIARIO % | MECHA >= +9% (Días) | CIERRE >= +9% (Días) | PROB MECHA %")
print("=========================================================================================")

for r in results[:25]:
    print(f"{r['rank']:<4} | {r['symbol']:<12} | {r['avg_range_pct']:<14}% | {r['spikes_high_9']}/{r['total_days']} días          | {r['spikes_close_9']}/{r['total_days']} días           | {r['prob_high_9_pct']}%")

avg_prob_high = sum(r['prob_high_9_pct'] for r in results) / len(results) if results else 0
avg_prob_close = sum(r['prob_close_9_pct'] for r in results) / len(results) if results else 0
avg_daily_range = sum(r['avg_range_pct'] for r in results) / len(results) if results else 0

print("\n--- RESUMEN CONSOLIDADO 365 DÍAS (TOP 50-100) ---")
print(f"1. Rango Diario Promedio del Top 50-100        : {avg_daily_range:.2f}%")
print(f"2. Probabilidad Diaria de tocar +9.0% (Mecha)  : {avg_prob_high:.1f}% de los días (~1 de cada 4.5 días)")
print(f"3. Probabilidad Diaria de CERRAR en +9.0%      : {avg_prob_close:.1f}% de los días (~1 de cada 10 días)")
print(f"4. Promedio de Oportunidades de +9.0% por Día  : En una lista de 50 monedas, hay en promedio {round((avg_prob_high/100)*50, 1)} mechas de +9% CADA DÍA.")

