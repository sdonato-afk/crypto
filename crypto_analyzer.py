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
                    # --- FILTRO CAPA 1: Excluir pares con keywords de stablecoins / apalancados ---
                    STABLE_BASE_ASSETS = {
                        'UP', 'DOWN', 'BEAR', 'BULL', 'FDUSD', 'USDC', 'TUSD', 'EUR',
                        'USD1', 'USD2', 'USD3', 'USDS', 'USDP', 'USDX', 'USDQ',
                        'BUSD', 'DAI', 'FRAX', 'LUSD', 'SUSD', 'PYUSD', 'USDD',
                        'OUSD', 'CUSD', 'GUSD', 'HUSD', 'EURS', 'EURC', 'EURI',
                        'PAX', 'AGEUR', 'AEUR', 'UST', 'USDN', 'USDT', 'WBTC', 'WETH'
                    }
                    usdt_pairs = [
                        d for d in data
                        if d['symbol'].endswith('USDT')
                        and d['symbol'][:-4] not in STABLE_BASE_ASSETS
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
        """BTC Guard: Monitorea flash crash de Bitcoin (> -1.2% en 15m)"""
        candles = self.fetch_klines("BTCUSDT", interval="5m", limit=6)
        if len(candles) < 5:
            return {"status": "OK", "reason": "Sin datos suficientes BTC", "drop_pct": 0.0}

        latest_close = candles[-1]["close"]
        prev_close = candles[-4]["close"]  # Cierre de hace ~20 min (4 velas × 5m), más estable
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
        Estrategia Combinada Avanzada: Geometría SWEEP 4H + Divergencia RSI + Absorción 2.5x + Filtro Iliquidez
        """
        symbol = crypto_item["symbol"]
        candles = self.fetch_klines(symbol, interval="5m", limit=60) # Últimas 5 horas (cobertura 4H + 1H)

        if not candles or len(candles) < 48:
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
        # Exige al menos $5,000 USD negociados en la última vela de 5 minutos
        quote_volume_5m = current_price * last_candle["volume"]
        if quote_volume_5m < 5000.0:
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
                "signal": "ILIQUIDEZ_ALTA 🔴"
            }

        high_2h = max(c["high"] for c in candles[-24:])
        dip_pct = ((current_price - high_2h) / high_2h) * 100.0
        
        total_range = c_high - c_low
        lower_wick = min(c_open, c_close) - c_low
        wick_ratio = (lower_wick / total_range) if total_range > 0 else 0.0

        prev_24_candles = candles[-25:-1]
        avg_volume = sum(c["volume"] for c in prev_24_candles) / len(prev_24_candles)
        volume_ratio = (last_candle["volume"] / avg_volume) if avg_volume > 0 else 1.0
        
        rsi_val = self.calculate_rsi(candles, period=14)

        # --- GEOMETRÍA 1: BARRIDO DE LIQUIDEZ 4H (SWEEP LIQUIDITY / Turtle Soup) ---
        # Identifica el mínimo más bajo de las últimas 4 horas (48 velas)
        low_4h = min(c["low"] for c in candles[-49:-1])
        is_sweep = (c_low < low_4h and c_close > low_4h and wick_ratio >= 0.40)

        # --- GEOMETRÍA 2: DIVERGENCIA ALCISTA RSI ---
        p_low_1 = min(c["low"] for c in candles[-24:-12])
        p_low_2 = min(c["low"] for c in candles[-12:])
        idx_l1 = len(candles) - 24 + [c["low"] for c in candles[-24:-12]].index(p_low_1)
        idx_l2 = len(candles) - 12 + [c["low"] for c in candles[-12:]].index(p_low_2)
        rsi_l1 = self.calculate_rsi(candles[:idx_l1+1])
        rsi_l2 = self.calculate_rsi(candles[:idx_l2+1])
        is_divergence = (p_low_2 < p_low_1 and rsi_l2 > rsi_l1 + 3.0 and rsi_l2 < 45.0)

        # Geometría 3: Compresión de Volatilidad (Squeeze)
        recent_ranges = [((c["high"] - c["low"]) / c["open"]) * 100.0 for c in candles[-6:-1]]
        avg_squeeze_range = (sum(recent_ranges) / len(recent_ranges)) if recent_ranges else 3.0
        is_squeeze = avg_squeeze_range < 1.8

        # Geometría 4: Doble Suelo Local (W-Bottom)
        recent_lows = [c["low"] for c in candles[-12:]]
        l1 = min(recent_lows[:6])
        l2 = min(recent_lows[6:])
        is_w_bottom = (abs(l1 - l2) / l1 <= 0.008) if l1 > 0 else False

        # --- MOTOR DE PUNTUACIÓN DE ALTA CONVICCIÓN ---
        score = 35.0

        # Filtro Anti-FOMO RSI
        if rsi_val > 75.0:
            score -= 30.0

        # Bonificación por Geometría Avanzada
        if is_sweep:
            score += 35.0  # +35 Pts por Barrido Institucional de 4H
        if is_divergence:
            score += 30.0  # +30 Pts por Divergencia Alcista RSI

        # Bonificación por Pico de Volumen Institucional (>= 2.5x)
        if volume_ratio >= 2.5 and c_close >= c_open:
            score += 20.0
        elif volume_ratio >= 2.0:
            score += 10.0

        # Bonificación por Absorción de Mecha (Wick >= 40%)
        if wick_ratio >= 0.40:
            score += 15.0

        # Bonificación por Geometría Complementaria
        if is_squeeze:
            score += 10.0
        if is_w_bottom:
            score += 10.0

        score = max(0.0, min(100.0, round(score, 1)))

        signal = "NEUTRAL"
        if score >= 75.0:
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
