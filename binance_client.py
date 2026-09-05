# binance_client.py - Cliente HMAC Ligero para Binance API (Sin dependencias externas pesadas)
import urllib.request
import urllib.parse
import json
import time
import hmac
import hashlib

class BinanceClient:
    def __init__(self, api_key, api_secret, dry_run=True):
        self.api_key = api_key
        self.api_secret = api_secret.encode('utf-8')
        self.base_url = "https://api.binance.com"
        self.dry_run = dry_run
        
    def _generate_signature(self, query_string):
        return hmac.new(self.api_secret, query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        
    def _request(self, method, endpoint, params=None):
        if not params:
            params = {}
        
        params['timestamp'] = int(time.time() * 1000)
        query_string = urllib.parse.urlencode(params)
        signature = self._generate_signature(query_string)
        
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        
        req = urllib.request.Request(url, method=method)
        req.add_header("X-MBX-APIKEY", self.api_key)
        req.add_header("User-Agent", "Mozilla/5.0")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"[BINANCE API ERROR] {endpoint}: {e.code} - {error_body}")
            return None
        except Exception as e:
            print(f"[BINANCE API ERROR] {endpoint} falló: {e}")
            return None

    def get_usdt_balance(self):
        """Obtiene el saldo real disponible de USDT en la cuenta Spot."""
        if not self.api_key or not self.api_secret:
            print("[WARN] No hay API keys configuradas. Simulando balance $0.")
            return 0.0
            
        data = self._request("GET", "/api/v3/account")
        if data and "balances" in data:
            for b in data["balances"]:
                if b["asset"] == "USDT":
                    return float(b["free"])
        return 0.0

    def place_market_order(self, symbol, side, qty):
        """
        Ejecuta una orden MARKET. 
        En modo DRY_RUN, se usa el endpoint /test (valida firmas y saldo sin ejecutar).
        """
        endpoint = "/api/v3/order/test" if self.dry_run else "/api/v3/order"
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{qty:.8f}".rstrip('0').rstrip('.') # Formato Binance
        }
        
        print(f"[API LIVE] Ejecutando {'TEST ' if self.dry_run else ''}orden {side} MARKET de {params['quantity']} {symbol}...")
        resp = self._request("POST", endpoint, params)
        return resp is not None

    def place_oco_order(self, symbol, qty, take_profit_price, stop_loss_price, stop_limit_price):
        """
        Coloca una orden OCO (Venta de Take Profit + Venta de Stop Loss simultáneas).
        No existe endpoint de test real para OCO, por lo que en DRY_RUN solo se simula.
        """
        params = {
            "symbol": symbol,
            "side": "SELL",
            "quantity": f"{qty:.8f}".rstrip('0').rstrip('.'),
            "price": f"{take_profit_price:.4f}",
            "stopPrice": f"{stop_loss_price:.4f}",
            "stopLimitPrice": f"{stop_limit_price:.4f}",
            "stopLimitTimeInForce": "GTC"
        }
        
        if self.dry_run:
            print(f"[API LIVE] (DRY_RUN) Simulando OCO {symbol} | QTY: {params['quantity']} | TP: {params['price']} | SL: {params['stopPrice']}")
            return True
            
        print(f"[API LIVE] Enviando OCO SELL {symbol} a Binance...")
        resp = self._request("POST", "/api/v3/order/oco", params)
        return resp is not None

    def cancel_all_orders(self, symbol):
        """Cancela todas las órdenes activas (incluyendo OCO) para un símbolo."""
        if self.dry_run:
            print(f"[API LIVE] (DRY_RUN) Simulando cancelación de órdenes para {symbol}")
            return True
        print(f"[API LIVE] Cancelando órdenes activas para {symbol}...")
        resp = self._request("DELETE", "/api/v3/openOrders", {"symbol": symbol})
        return resp is not None

    def close_market(self, symbol, qty):
        """Cierra una posición por Market (emergencia o trailing trigger)."""
        endpoint = "/api/v3/order/test" if self.dry_run else "/api/v3/order"
        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{qty:.8f}".rstrip('0').rstrip('.')
        }
        print(f"[API LIVE] Ejecutando {'TEST ' if self.dry_run else ''} MARKET SELL para {symbol}")
        resp = self._request("POST", endpoint, params)
        return resp is not None
