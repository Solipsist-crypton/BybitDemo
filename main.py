import os
import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import strategy

# --- ЧИТАННЯ ЗМІННИХ З СЕРВЕРА ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- КОНФІГУРАЦІЯ ---
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
QTY_LIST = {
    "BTCUSDT": 0.001, 
    "ETHUSDT": 0.01, 
    "SOLUSDT": 1.0, 
    "XRPUSDT": 100.0, 
    "ADAUSDT": 100.0
}
LEVERAGE = 10

# Підключення до Demo-серверу Bybit
session = HTTP(
    testnet=False, 
    demo=True, 
    api_key=API_KEY, 
    api_secret=API_SECRET,
    recv_window=60000
)

def send_tg_with_buttons(message):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "📊 Мої Позиції", "url": "https://www.bybit.com/trading-demo/v5/trade/futures/BTCUSDT"}],
                [{"text": "📈 Оновити статус", "callback_data": "refresh"}]
            ]
        }
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Помилка TG: {e}")

def get_candles(symbol):
    try:
        res = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
        df = pd.DataFrame(res['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
        df['close'] = df['close'].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except:
        return None

def manage_positions():
    """Функція для перевірки та підтягування Trailing Stop"""
    try:
        positions = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
        for p in positions:
            if float(p['size']) > 0:
                symbol = p['symbol']
                side = p['side']
                curr_price = float(p['markPrice'])
                curr_sl = float(p['stopLoss']) if p['stopLoss'] else 0
                
                new_sl = strategy.calculate_trailing_stop(curr_sl, curr_price, side)
                
                # Якщо стоп змінився суттєво (наприклад, більше ніж на 0.1%), оновлюємо
                if abs(new_sl - curr_sl) > (curr_price * 0.001):
                    session.set_trading_stop(
                        category="linear", symbol=symbol, 
                        stopLoss=str(round(new_sl, 4)), slTriggerBy="MarkPrice"
                    )
    except Exception as e:
        print(f"Помилка трейлінгу: {e}")

def run_bot():
    send_tg_with_buttons("🎯 СНАЙПЕР ЗАПУЩЕНИЙ (DEMO)\nРежим: Trailing Stop Активовано.\nМонети: BTC, ETH, SOL, XRP, ADA")
    
    while True:
        # 1. Перевірка сигналів для відкриття нових угод
        for symbol in SYMBOLS:
            df = get_candles(symbol)
            if df is not None:
                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    try:
                        order = session.place_order(
                            category="linear", symbol=symbol, side=side,
                            orderType="Market", qty=str(QTY_LIST[symbol])
                        )
                        send_tg_with_buttons(f"🚀 ВХІД У ПОЗИЦІЮ!\n🔥 {symbol} | {side}\n💸 Ціна: {df['close'].iloc[-1]}")
                    except Exception as e:
                        print(f"Помилка ордера {symbol}: {e}")
            time.sleep(1) # Пауза між монетами

        # 2. Управління вже відкритими позиціями (Trailing Stop)
        manage_positions()
        
        print(f"⏱ [{time.strftime('%H:%M:%S')}] Скан завершено. Чекаю 60с...")
        time.sleep(60)

if __name__ == "__main__":
    run_bot()