import os
import time
import telebot
import pandas as pd
from pybit.unified_trading import HTTP
import strategy
from threading import Thread

# --- КОНФІГУРАЦІЯ З VARIABLE СЕРВЕРА ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Налаштування активів та об'ємів
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
QTY_LIST = {
    "BTCUSDT": 0.001, 
    "ETHUSDT": 0.01, 
    "SOLUSDT": 1.0, 
    "XRPUSDT": 100.0, 
    "ADAUSDT": 100.0
}

# Ініціалізація клієнтів
bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(
    testnet=False, 
    demo=True, 
    api_key=API_KEY, 
    api_secret=API_SECRET,
    recv_window=60000
)

def get_report():
    """Створює звіт про поточні профіти без входу в Bybit"""
    try:
        pos = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
        active = [p for p in pos if float(p['size']) > 0]
        
        if not active:
            return "📭 Активних позицій немає. Бот у пошуку сигналу."
        
        report = "📊 АНАЛІЗ УГОД:\n"
        total_pnl = 0
        for p in active:
            pnl = float(p['unrealisedPnl'])
            total_pnl += pnl
            report += f"🔹 {p['symbol']} | {p['side']}\n   PnL: {pnl:.2f} USDT\n"
        
        report += f"\n💰 ЗАГАЛЬНИЙ ПРОФІТ: {total_pnl:.2f} USDT"
        return report
    except Exception as e:
        return f"❌ Помилка API: {e}"

@bot.callback_query_handler(func=lambda call: call.data == "refresh")
def callback_refresh(call):
    """Оновлення статусу при натисканні кнопки"""
    status_text = get_report()
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("📈 Оновити статус", callback_data="refresh"))
    try:
        bot.edit_message_text(status_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except:
        pass

def trading_loop():
    """Основний цикл: сканування ринку та управління стопами"""
    print("🚀 Цикл торгівлі запущено...")
    while True:
        try:
            # 1. Отримуємо всі відкриті позиції одним запитом для перевірки дублів
            pos_data = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            open_symbols = [p['symbol'] for p in pos_data if float(p['size']) > 0]

            for symbol in SYMBOLS:
                # ЗАХИСТ: Якщо по монеті вже є позиція — не шукаємо новий вхід
                if symbol in open_symbols:
                    continue

                # Отримання даних для аналізу
                res = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(res['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                # Перевірка сигналу через strategy.py
                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    session.place_order(
                        category="linear", symbol=symbol, side=side, 
                        orderType="Market", qty=str(QTY_LIST[symbol])
                    )
                    bot.send_message(TG_CHAT_ID, f"🚀 НОВА УГОДА: {symbol} | {side}\nВхід за стратегією EMA.")

                time.sleep(2) # Пауза щоб не спамити API

            # 2. Управління Trailing Stop для всіх відкритих позицій
            for p in pos_data:
                if float(p['size']) > 0:
                    symbol = p['symbol']
                    side = p['side']
                    curr_price = float(p['markPrice'])
                    curr_sl = float(p['stopLoss']) if p['stopLoss'] else 0
                    
                    # Розрахунок нового стопа через strategy.py
                    new_sl = strategy.calculate_trailing_stop(curr_sl, curr_price, side)
                    
                    # Оновлюємо, якщо новий стоп вигідніший на 0.1%
                    if abs(new_sl - curr_sl) > (curr_price * 0.001):
                        session.set_trading_stop(
                            category="linear", symbol=symbol, 
                            stopLoss=str(round(new_sl, 4)), slTriggerBy="MarkPrice"
                        )

        except Exception as e:
            print(f"⚠️ Помилка в циклі: {e}")
            if "403" in str(e): time.sleep(300) # Спимо 5 хв при блокуванні IP
        
        time.sleep(60) # Скан кожну хвилину

if __name__ == "__main__":
    # Запуск торгівлі в окремому фоновому потоці
    Thread(target=trading_loop, daemon=True).start()
    
    # Створення інтерфейсу в Telegram
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("📈 Оновити статус", callback_data="refresh"))
    
    bot.send_message(
        TG_CHAT_ID, 
        "🤖 Бот-Снайпер активований!\n\nЛогіка: EMA 13/34/89\nРежим: 1 монета = 1 позиція\nТрейлінг-стоп: Увімкнено", 
        reply_markup=markup
    )
    
    # Запуск прослуховування кнопок
    bot.polling(none_stop=True)