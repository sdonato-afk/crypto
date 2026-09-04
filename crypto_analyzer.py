# crypto_analyzer.py - Motor de Análisis Cuantitativo y Absorción de Volumen
# Implementa: BTC Guard (Freno Macro) + Absorción de Volumen + Dip Detection

import json
import urllib.request
import time

class CryptoAnalyzer:
    def __init__(self):
        self.binance_klines_url = "https://api.binance.com/api/v3/klines"
        self.binance_ticker_url = "https://api.binance.com/api/v3/ticker/24hr"

    def fetch_klines(self, symbol, interval="5m", limit=30):
        """Consulta velas de temporalidad corta (5m) para detectar absorción de volumen"""
        url = f"{self.binance_klines_url}?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                # Formato KLine: [open_time, open, high, low, close, volume, ...]
                candles = []
                for k in data:
                    candles.append({
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                return candles
        except Exception:
            return []

    def check_btc_guard(self):
        """
        BTC Guard: Monitorea Bitcoin en tiempo real.
        Si BTC sufre un flash crash (> -1.2% en velas de 5m reciente), 
        activa el Freno de Mano de Mercado para evitar abrir altcoins en caída libre.
        """
        candles = self.fetch_klines("BTCUSDT", interval="5m", limit=6)
        if len(candles) < 3:
            return {"status": "OK", "reason": "Sin datos suficientes BTC", "drop_pct": 0.0}

        latest_close = candles[-1]["close"]
        prev_close = candles[-3]["open"] # Cambio en los últimos ~15 minutos

        drop_pct = ((latest_close - prev_close) / prev_close) * 100.0

        if drop_pct <= -1.2:
            return {
                "status": "PANIC_LOCK",
                "reason": f"🚨 ALERTA BTC FLASH CRASH: BTC cayó {drop_pct:.2f}% en 15m. Mercado Congelado.",
                "drop_pct": round(drop_pct, 2)
            }

        return {
            "status": "NORMAL",
            "reason": "Mercado BTC Estable / Alcista",
            "drop_pct": round(drop_pct, 2)
        }

    def analyze_volume_absorption(self, crypto_item):
        """
        Estrategia Diferenciada: Dip & Volume Absorption
        Busca activos del Top 20 que:
        1. Hayan tenido una caída previa (Dip)
        2. Muestren una vela de absorción con mecha inferior (Whale absorption)
        3. Tengan un volumen comprador 2.0x o superior al promedio
        """
        symbol = crypto_item["symbol"]
        candles = self.fetch_klines(symbol, interval="5m", limit=24) # Últimas 2 horas

        if not candles or len(candles) < 12:
            return {
                "ticker": crypto_item["ticker"],
                "name": crypto_item["name"],
                "symbol": symbol,
                "price": 0.0,
                "score": 0.0,
                "signal": "SIN_DATOS",
                "volume_ratio": 1.0,
                "wick_ratio": 0.0
            }

        current_price = candles[-1]["close"]
        high_2h = max(c["high"] for c in candles)
        low_2h = min(c["low"] for c in candles)

        # 1. Porcentaje de caída desde el máximo de 2 horas (Dip Check)
        dip_pct = ((current_price - high_2h) / high_2h) * 100.0

        # 2. Análisis de la última vela (Mecha inferior vs Cuerpo)
        last_candle = candles[-1]
        c_open = last_candle["open"]
        c_close = last_candle["close"]
        c_high = last_candle["high"]
        c_low = last_candle["low"]
        
        total_range = c_high - c_low
        body_size = abs(c_close - c_open)
        lower_wick = min(c_open, c_close) - c_low

        wick_ratio = (lower_wick / total_range) if total_range > 0 else 0.0

        # 3. Ratio de Volumen vs Promedio de 20 períodos
        avg_volume = sum(c["volume"] for c in candles[:-1]) / (len(candles) - 1)
        volume_ratio = (last_candle["volume"] / avg_volume) if avg_volume > 0 else 1.0

        # 4. Cálculo del Score Cuantitativo Diferenciado (0 a 100)
        score = 40.0

        # Bajar puntaje si está sobrecomprado o en máximo absoluto
        if current_price >= high_2h * 0.99:
            score -= 15.0 # Evita comprar en el pico del gráfico

        # Bonificación por Caída Controlada (Dip ideal entre -1.5% y -4.5%)
        if -4.5 <= dip_pct <= -1.5:
            score += 25.0
        elif dip_pct < -6.0:
            score -= 20.0 # Caída demasiado violenta (Cuchillo cayendo)

        # Bonificación por Absorción de Mecha (Whale Wick > 40% del rango)
        if wick_ratio >= 0.40:
            score += 20.0

        # Bonificación por Pico de Volumen Comprador
        if volume_ratio >= 2.0 and c_close >= c_open:
            score += 20.0
        elif volume_ratio >= 1.5:
            score += 10.0

        score = max(0.0, min(100.0, round(score, 1)))

        signal = "NEUTRAL"
        if score >= 70.0:
            signal = "ABSORCION_ALCISTA 🟢"
        elif score <= 35.0:
            signal = "RIESGO_ALTO 🔴"

        return {
            "ticker": crypto_item["ticker"],
            "name": crypto_item["name"],
            "symbol": symbol,
            "price": current_price,
            "dip_pct": round(dip_pct, 2),
            "wick_ratio": round(wick_ratio * 100, 1),
            "volume_ratio": round(volume_ratio, 2),
            "score": score,
            "signal": signal
        }

    def rank_top_20(self, crypto_list):
        """Analiza y ordena los activos de mayor a menor potencial por Absorción de Volumen"""
        results = []
        btc_status = self.check_btc_guard()

        for item in crypto_list:
            analysis = self.analyze_volume_absorption(item)
            analysis["btc_guard_status"] = btc_status["status"]
            analysis["btc_guard_reason"] = btc_status["reason"]
            results.append(analysis)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results, btc_status
