import os
import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import strategy  # Твоя логіка EMA 13/34/89

# --- ЗАВАНТАЖЕННЯ КОНФІГУРАЦІЇ ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- НАЛАШТУВАННЯ ТОРГІВЛІ ---
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
# Об'єми підібрані приблизно на $50-100 з плечем 10x
QTY_LIST = {
    "BTCUSDT": 0.001, 
    "ETHUSDT": 0.01, 
    "SOLUSDT": 1.0, 
    "XRPUSDT": 100.0, 
    "ADAUSDT": 100.0
}

session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)

def send_tg(message):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": message})
    except Exception as e:
        print(f"❌ Помилка Telegram: {e}")

def get_candles(symbol):
    try:
        res = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
        df = pd.DataFrame(res['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
        df['close'] = df['close'].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except:
        return None

def run_bot():
    send_tg("🤖 Бот-Снайпер запущений на сервері!\nМонети: " + ", ".join(SYMBOLS))
    
    while True:
        for symbol in SYMBOLS:
            try:
                df = get_candles(symbol)
                if df is not None:
                    signal = strategy.check_signals(df)
                    price = df['close'].iloc[-1]
                    
                    if signal != "WAIT":
                        side = "Buy" if signal == "BUY" else "Sell"
                        session.place_order(
                            category="linear", symbol=symbol, side=side,
                            orderType="Market", qty=str(QTY_LIST[symbol])
                        )
                        send_tg(f"🔔 СИГНАЛ: {signal}\n💰 Монета: {symbol}\n📈 Ціна: {price}")
                
                time.sleep(2) # Коротка пауза між монетами
                
            except Exception as e:
                print(f"⚠️ Помилка по {symbol}: {e}")
        
        print(f"⏱ [{time.strftime('%H:%M:%S')}] Скан завершено. Чекаю 1 хв...")
        time.sleep(60)

if __name__ == "__main__":
    run_bot()