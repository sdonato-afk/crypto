# crypto_analyzer.py - Motor de Análisis Cuantitativo, Geometría y Absorción de Volumen
# Implementa: BTC Guard + Absorción de Volumen (2.5x) + Geometría (Squeeze / W-Bottom) + Filtro RSI < 75

import json
import urllib.request
import time

class CryptoAnalyzer:
    def __init__(self):
        self.binance_klines_url = "https://data-api.binance.vision/api/v3/klines"
        self.binance_ticker_url = "https://data-api.binance.vision/api/v3/ticker/24hr"

    def fetch_klines(self, symbol, interval="5m", limit=30):
        """Consulta velas de temporalidad corta para análisis técnico (con reintentos)"""
        import urllib.parse
        safe_symbol = urllib.parse.quote(str(symbol).strip())
        url = f"{self.binance_klines_url}?symbol={safe_symbol}&interval={interval}&limit={limit}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as resp:
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
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    print(f"[WARN] fetch_klines({symbol}) fallo tras 3 intentos: {e}")
                    return []
        return []  # Guardia defensiva

    def fetch_ticker_price(self, symbol):
        """Consulta precio actual de un ticker específico (para slots que salieron del Top 50-100)"""
        url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    return float(data["price"])
            except Exception:
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
        return 0.0

    def get_top_50_100_symbols(self):
        """Obtiene las 50 criptomonedas ubicadas entre el ranking 50 y 100 por volumen en Binance (con reintentos)"""
        for attempt in range(3):
            try:
                req = urllib.request.Request(self.binance_ticker_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    # --- FILTRO CAPA 1: Excluir pares con keywords de stablecoins / apalancados y Monedas Tóxicas ---
                    STABLE_BASE_ASSETS = {
                        'UP', 'DOWN', 'BEAR', 'BULL', 'FDUSD', 'USDC', 'TUSD', 'EUR',
                        'USD1', 'USD2', 'USD3', 'USDS', 'USDP', 'USDX', 'USDQ',
                        'BUSD', 'DAI', 'FRAX', 'LUSD', 'SUSD', 'PYUSD', 'USDD',
                        'OUSD', 'CUSD', 'GUSD', 'HUSD', 'EURS', 'EURC', 'EURI',
                        'PAX', 'AGEUR', 'AEUR', 'UST', 'USDN', 'USDT', 'WBTC', 'WETH'
                    }
                    STATIC_TOXIC_BLACKLIST = {
                        'BCH', 'THE', 'SEI', 'HOLO', 'XPL'
                    }
                    usdt_pairs = [
                        d for d in data
                        if d['symbol'].endswith('USDT')
                        and d['symbol'][:-4] not in STABLE_BASE_ASSETS
                        and d['symbol'][:-4] not in STATIC_TOXIC_BLACKLIST
                    ]

                    usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)

                    # --- FILTRO CAPA 2: microtokens (<$0.001) y activos sin volatilidad (stablecoins disfrazadas) ---
                    # Un activo real siempre tiene >0.5% de movimiento diario.
                    # Una stablecoin (aunque cotice a $1 o a cualquier precio) casi no se mueve.
                    usdt_pairs = [
                        p for p in usdt_pairs
                        if float(p['lastPrice']) >= 0.001
                        and abs(float(p.get('priceChangePercent', 99))) >= 0.5
                    ]

                    import os
                    raw_srv = os.environ.get("RENDER_SERVICE_NAME", "").lower()
                    srv = raw_srv.replace("-", "").replace("_", "").strip()
                    if any(k in srv for k in ["nodo3", "nodo4", "nodo7", "nodob", "exotico"]):
                        def_start, def_end = 51, 100
                    elif any(k in srv for k in ["nodo5", "nodo8", "nodoc", "rebote"]):
                        def_start, def_end = 25, 75
                    else:
                        def_start, def_end = 1, 50

                    u_start = int(os.environ.get("UNIVERSE_START", def_start))
                    u_end   = int(os.environ.get("UNIVERSE_END", def_end))
                    top_slice = usdt_pairs[u_start:u_end]

                    results = []
                    for p in top_slice:
                        symbol = p['symbol']
                        ticker = symbol.replace('USDT', '')
                        results.append({"ticker": ticker, "name": ticker, "symbol": symbol})
                    return results
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    print(f"[WARN] get_top_50_100_symbols() fallo tras 3 intentos: {e}")
                    return []
        return []  # Guardia defensiva

    def check_btc_guard(self):
        """BTC Guard: Monitorea Tendencia Macro EMA 50 en 4H / D1 de Bitcoin"""
        candles = self.fetch_klines("BTCUSDT", interval="4h", limit=60)
        if len(candles) < 50:
            return {"status": "OK", "reason": "Sin datos suficientes BTC", "drop_pct": 0.0}

        closes = [c["close"] for c in candles]
        latest_close = closes[-1]
        
        # Calcular EMA 50 en 4H
        k = 2.0 / (50.0 + 1.0)
        ema50 = sum(closes[:50]) / 50.0
        for val in closes[50:]:
            ema50 = (val * k) + (ema50 * (1.0 - k))
            
        drop_pct = ((latest_close - closes[-6]) / closes[-6]) * 100.0 if len(closes) >= 6 else 0.0

        if latest_close < ema50:
            return {
                "status": "MACRO_BEAR_PAUSE",
                "reason": f"[MACRO PAUSE] BTC (${latest_close:.1f}) por debajo de EMA 50 4H (${ema50:.1f}). Compras Congeladas.",
                "drop_pct": round(drop_pct, 2)
            }

        return {
            "status": "NORMAL",
            "reason": f"[MACRO NORMAL] Mercado BTC Alcista (${latest_close:.1f} >= EMA50 ${ema50:.1f})",
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
        Estrategia SWING TRADING (4H / 7 Días): Geometría SWEEP 7D + Divergencia RSI 4H + Absorción 1.8x + Filtro Iliquidez
        """
        symbol = crypto_item["symbol"]
        candles = self.fetch_klines(symbol, interval="4h", limit=50) # Últimas 50 velas de 4H (~8.3 días de datos)

        if not candles or len(candles) < 42:
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
        last_candle = candles[-1]
        c_open = last_candle["open"]
        c_close = last_candle["close"]
        c_high = last_candle["high"]
        c_low = last_candle["low"]
        
        # --- FILTRO 1: ANTI-ILIQUIDEZ / ANTI-FLASH CRASH (Anti-TUT) ---
        # Exige al menos $100,000 USD negociados por vela de 4H
        quote_volume_4h = current_price * last_candle["volume"]
        if quote_volume_4h < 100000.0:
            return {
                "ticker": crypto_item["ticker"],
                "name": crypto_item["name"],
                "symbol": symbol,
                "price": current_price,
                "dip_pct": 0.0,
                "wick_ratio": 0.0,
                "volume_ratio": 0.0,
                "rsi": 50.0,
                "score": 0.0,
                "signal": "ILIQUIDEZ_ALTA"
            }

        high_7d = max(c["high"] for c in candles[-42:])
        dip_pct = ((current_price - high_7d) / high_7d) * 100.0
        
        total_range = c_high - c_low
        lower_wick = min(c_open, c_close) - c_low
        wick_ratio = (lower_wick / total_range) if total_range > 0 else 0.0

        prev_42_candles = candles[-43:-1]
        avg_volume = sum(c["volume"] for c in prev_42_candles) / len(prev_42_candles)
        volume_ratio = (last_candle["volume"] / avg_volume) if avg_volume > 0 else 1.0
        
        rsi_val = self.calculate_rsi(candles, period=14)

        # --- SWING GEOMETRÍA 1: BARRIDO DE MÍNIMOS DE 7 DÍAS (4H SWEEP / Turtle Soup) ---
        low_7d = min(c["low"] for c in candles[-43:-1])
        is_swing_sweep = (c_low < low_7d and c_close > low_7d and wick_ratio >= 0.35)

        # --- SWING GEOMETRÍA 2: DIVERGENCIA ALCISTA RSI 4H ---
        p_low_1 = min(c["low"] for c in candles[-30:-15])
        p_low_2 = min(c["low"] for c in candles[-15:])
        idx_l1 = len(candles) - 30 + [c["low"] for c in candles[-30:-15]].index(p_low_1)
        idx_l2 = len(candles) - 15 + [c["low"] for c in candles[-15:]].index(p_low_2)
        rsi_l1 = self.calculate_rsi(candles[:idx_l1+1])
        rsi_l2 = self.calculate_rsi(candles[:idx_l2+1])
        is_divergence = (p_low_2 < p_low_1 and rsi_l2 > rsi_l1 + 2.5 and rsi_l2 < 48.0)

        # --- MOTOR DE PUNTUACIÓN DE SWING TRADING ---
        score = 35.0

        # Filtro Anti-FOMO RSI 4H
        if rsi_val > 72.0:
            score -= 30.0

        # Bonificación por Geometría Swing 4H
        if is_swing_sweep:
            score += 35.0  # +35 Pts por Barrido de Mínimos de 7 Días
        if is_divergence:
            score += 30.0  # +30 Pts por Divergencia Alcista en 4H

        # Bonificación por Volumen Institucional 4H (>= 1.8x)
        if volume_ratio >= 1.8 and c_close >= c_open:
            score += 20.0
        elif volume_ratio >= 1.5:
            score += 10.0

        # Bonificación por Absorción de Mecha 4H (Wick >= 35%)
        if wick_ratio >= 0.35:
            score += 15.0

        score = max(0.0, min(100.0, round(score, 1)))

        signal = "NEUTRAL"
        if score >= 70.0:
            signal = "ABSORCION_ALCISTA"
        elif score <= 35.0:
            signal = "RIESGO_ALTO"

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

    def rank_universe(self, crypto_list=None):
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
