from binance_client import BinanceClient
c = BinanceClient('FAKE_KEY', 'FAKE_SECRET')
print(f'Balance: {c.get_usdt_balance()}')
print(f'Market Test: {c.place_market_order("BTCUSDT", "BUY", 0.01)}')
