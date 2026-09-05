# crypto_analyzer.py - Motor de Análisis Cuantitativo, Geometría y Absorción de Volumen
# Implementa: BTC Guard + Absorción de Volumen (2.5x) + Geometría (Squeeze / W-Bottom) + Filtro RSI < 75

import json
import urllib.request
import time

class CryptoAnalyzer:
    def __init__(self):
        self.binance_klines_url = "https://api.binance.com/api/v3/klines"
        self.binance_ticker_url = "https://api.binance.com/api/v3/ticker/24hr"

    def fetch_klines(self, symbol, interval="5m", limit=30):
        """Consulta velas de temporalidad corta para análisis técnico"""
        url = f"{self.binance_klines_url}?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
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

    def get_top_50_100_symbols(self):
        """Obtiene las 50 criptomonedas ubicadas entre el ranking 50 y 100 por volumen en Binance"""
        try:
            req = urllib.request.Request(self.binance_ticker_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                usdt_pairs = [d for d in data if d['symbol'].endswith('USDT') and not d['symbol'].startswith('UP') and not d['symbol'].startswith('DOWN') and not 'BEAR' in d['symbol'] and not 'BULL' in d['symbol'] and not 'FDUSD' in d['symbol'] and not 'USDC' in d['symbol'] and not 'TUSD' in d['symbol'] and not 'EUR' in d['symbol']]
                usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
                top_50_100 = usdt_pairs[50:100]
                
                results = []
                for p in top_50_100:
                    symbol = p['symbol']
                    ticker = symbol.replace('USDT', '')
                    results.append({"ticker": ticker, "name": ticker, "symbol": symbol})
                return results
        except Exception:
            return []

    def check_btc_guard(self):
        """BTC Guard: Monitorea flash crash de Bitcoin (> -1.2% en 15m)"""
        candles = self.fetch_klines("BTCUSDT", interval="5m", limit=6)
        if len(candles) < 3:
            return {"status": "OK", "reason": "Sin datos suficientes BTC", "drop_pct": 0.0}

        latest_close = candles[-1]["close"]
        prev_close = candles[-3]["open"]
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

    def calculate_rsi(self, candles, period=14):
        if len(candles) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(candles)):
            diff = candles[i]["close"] - candles[i-1]["close"]
            gains.append(diff if diff >= 0 else 0.0)
            losses.append(abs(diff) if diff < 0 else 0.0)
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100.0
        return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

    def analyze_volume_absorption(self, crypto_item):
        """
        Estrategia Combinada: Volume Surge + Geometría Squeeze/W-Bottom + Filtro RSI < 75
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
                "wick_ratio": 0.0,
                "rsi": 50.0
            }

        current_price = candles[-1]["close"]
        high_2h = max(c["high"] for c in candles)
        low_2h = min(c["low"] for c in candles)
        dip_pct = ((current_price - high_2h) / high_2h) * 100.0

        last_candle = candles[-1]
        c_open = last_candle["open"]
        c_close = last_candle["close"]
        c_high = last_candle["high"]
        c_low = last_candle["low"]
        
        total_range = c_high - c_low
        lower_wick = min(c_open, c_close) - c_low
        wick_ratio = (lower_wick / total_range) if total_range > 0 else 0.0

        avg_volume = sum(c["volume"] for c in candles[:-1]) / (len(candles) - 1)
        volume_ratio = (last_candle["volume"] / avg_volume) if avg_volume > 0 else 1.0
        
        rsi_val = self.calculate_rsi(candles, period=14)

        # Geometría 1: Compresión de Volatilidad (Squeeze)
        recent_ranges = [((c["high"] - c["low"]) / c["open"]) * 100.0 for c in candles[-6:-1]]
        avg_squeeze_range = (sum(recent_ranges) / len(recent_ranges)) if recent_ranges else 3.0
        is_squeeze = avg_squeeze_range < 1.8

        # Geometría 2: Doble Suelo Local (W-Bottom)
        recent_lows = [c["low"] for c in candles[-12:]]
        l1 = min(recent_lows[:6])
        l2 = min(recent_lows[6:])
        is_w_bottom = (abs(l1 - l2) / l1 <= 0.008)

        score = 40.0

        # Filtro Anti-FOMO RSI
        if rsi_val > 75.0:
            score -= 30.0 # Descartar sobrecompra extrema en la cima

        # Bonificación por Pico de Volumen Institucional (>= 2.5x)
        if volume_ratio >= 2.5 and c_close >= c_open:
            score += 25.0
        elif volume_ratio >= 2.0:
            score += 15.0

        # Bonificación por Absorción de Mecha (Wick > 40%)
        if wick_ratio >= 0.40:
            score += 20.0

        # Bonificación por Geometría Squeeze o W-Bottom
        if is_squeeze:
            score += 20.0
        if is_w_bottom:
            score += 15.0

        if -4.5 <= dip_pct <= -1.5:
            score += 15.0

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
            "rsi": round(rsi_val, 1),
            "score": score,
            "signal": signal
        }

    def rank_top_20(self, crypto_list=None):
        """Analiza y ordena los activos del Top 50-100 por Absorción de Volumen y Geometría"""
        results = []
        btc_status = self.check_btc_guard()

        if not crypto_list:
            crypto_list = self.get_top_50_100_symbols()

        for item in crypto_list:
            analysis = self.analyze_volume_absorption(item)
            analysis["btc_guard_status"] = btc_status["status"]
            analysis["btc_guard_reason"] = btc_status["reason"]
            results.append(analysis)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results, btc_status
