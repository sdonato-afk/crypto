# analizar_volatilidad_top100.py - Análisis cuantitativo de volatilidad Top 100 en Binance (Sin numpy)
import urllib.request
import json
import time
import sys
import statistics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== INICIANDO ESTUDIO CUANTITATIVO DE VOLATILIDAD TOP 100 EN BINANCE ===")

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

top_100 = usdt_pairs[:100]
print(f"Top 100 pares por volumen obtenidos. Analizando velas diarias de los últimos 6 meses (180 días)...")

results = []

for idx, p in enumerate(top_100):
    symbol = p['symbol']
    url_klines = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=180"
    try:
        req_k = urllib.request.Request(url_klines, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_k, timeout=5) as resp:
            klines = json.loads(resp.read().decode('utf-8'))
            
            if len(klines) < 30:
                continue

            daily_ranges_pct = []
            max_spikes_6pct = 0
            daily_returns = []

            for k in klines:
                op = float(k[1])
                hi = float(k[2])
                lo = float(k[3])
                cl = float(k[4])
                
                if op > 0:
                    day_range = ((hi - lo) / op) * 100.0
                    daily_ranges_pct.append(day_range)
                    
                    up_wick_pct = ((hi - op) / op) * 100.0
                    if up_wick_pct >= 6.0:
                        max_spikes_6pct += 1
                        
                    ret = ((cl - op) / op) * 100.0
                    daily_returns.append(ret)

            avg_volatility = sum(daily_ranges_pct) / len(daily_ranges_pct)
            std_dev = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0
            spike_freq_pct = (max_spikes_6pct / len(klines)) * 100.0

            results.append({
                "symbol": symbol,
                "rank": idx + 1,
                "volume_24h_m": float(p['quoteVolume']) / 1_000_000,
                "avg_daily_range_pct": round(avg_volatility, 2),
                "std_dev_pct": round(std_dev, 2),
                "spikes_6pct_days": max_spikes_6pct,
                "total_days": len(klines),
                "spike_probability_pct": round(spike_freq_pct, 1)
            })
            
    except Exception as e:
        pass
    time.sleep(0.04)

results.sort(key=lambda x: x['spike_probability_pct'], reverse=True)

print("\n=========================================================================================")
print("RANK | TICKER       | VOL 24H (M$) | RANGO DIARIO PROM % | VELAZOS >+6% (Días) | PROB %")
print("=========================================================================================")

for r in results[:35]:
    print(f"{r['rank']:<4} | {r['symbol']:<12} | ${r['volume_24h_m']:<10.1f} | {r['avg_daily_range_pct']:<17}% | {r['spikes_6pct_days']}/{r['total_days']} días        | {r['spike_probability_pct']}%")

print("\n--- COMPARATIVA POR GRUPOS DE VOLUMEN / MARKET CAP ---")

top_10 = [r for r in results if r['rank'] <= 10]
top_10_20 = [r for r in results if 10 < r['rank'] <= 20]
mid_cap_20_50 = [r for r in results if 20 < r['rank'] <= 50]
alt_cap_50_100 = [r for r in results if 50 < r['rank'] <= 100]

def group_stats(group, name):
    if not group: return
    avg_vol = sum(g['avg_daily_range_pct'] for g in group) / len(group)
    avg_spike = sum(g['spike_probability_pct'] for g in group) / len(group)
    print(f"{name:<35}: Volatilidad Promedio = {avg_vol:.2f}% | Frecuencia Spike >=+6% = {avg_spike:.1f}% de los días")

group_stats(top_10, "Top 1-10 (Mega Caps: BTC, ETH...)")
group_stats(top_10_20, "Top 11-20 (Large Caps: SOL, AVAX...)")
group_stats(mid_cap_20_50, "Top 21-50 (Mid Caps: NEAR, FET, INJ)")
group_stats(alt_cap_50_100, "Top 51-100 (High Volatility Altcoins)")

