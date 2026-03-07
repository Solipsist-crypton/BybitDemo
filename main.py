import os
import time
import telebot
import pandas as pd
from pybit.unified_trading import HTTP
import strategy
from threading import Thread

# --- КОНФІГУРАЦІЯ ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
QTY_LIST = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 1.0, "XRPUSDT": 100.0, "ADAUSDT": 100.0}

bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)

def get_report():
    """Створює текстовий звіт про поточний стан"""
    try:
        pos = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
        active = [p for p in pos if float(p['size']) > 0]
        
        if not active:
            return "📭 Активних позицій немає."
        
        report = "📊 ПОТОЧНИЙ СТАТУС:\n"
        total_pnl = 0
        for p in active:
            pnl = float(p['unrealisedPnl'])
            total_pnl += pnl
            report += f"🔹 {p['symbol']} | {p['side']}\n   PnL: {pnl:.2f} USDT\n"
        
        report += f"\n💰 ЗАГАЛЬНИЙ PnL: {total_pnl:.2f} USDT"
        return report
    except Exception as e:
        return f"❌ Помилка отримання даних: {e}"

# Обробка натискання кнопки "Оновити статус"
@bot.callback_query_handler(func=lambda call: call.data == "refresh")
def callback_refresh(call):
    status_text = get_report()
    # Створюємо кнопки знову, щоб вони не зникли
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("📈 Оновити статус", callback_data="refresh"))
    bot.edit_message_text(status_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def trading_loop():
    """Основний цикл бота (торгівля + трейлінг)"""
    while True:
        for symbol in SYMBOLS:
            try:
                # Отримання свічок та перевірка сигналів
                res = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(res['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(QTY_LIST[symbol]))
                    bot.send_message(TG_CHAT_ID, f"🚀 НОВА УГОДА: {symbol} | {side}")

                # Трейлінг стоп
                positions = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
                for p in positions:
                    if float(p['size']) > 0 and p['symbol'] == symbol:
                        new_sl = strategy.calculate_trailing_stop(float(p['stopLoss'] or 0), float(p['markPrice']), p['side'])
                        if abs(new_sl - float(p['stopLoss'] or 0)) > (float(p['markPrice']) * 0.001):
                            session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(round(new_sl, 4)), slTriggerBy="MarkPrice")

            except Exception as e:
                print(f"Помилка {symbol}: {e}")
        time.sleep(60)

if __name__ == "__main__":
    # Запускаємо торгівлю в окремому потоці, щоб Telegram завжди відповідав на кнопки
    Thread(target=trading_loop).start()
    
    # Початкове повідомлення
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("📈 Оновити статус", callback_data="refresh"))
    bot.send_message(TG_CHAT_ID, "🎯 Снайпер онлайн! Трейлінг та кнопки активовані.", reply_markup=markup)
    
    # Запуск прослуховування кнопок
    bot.polling(none_stop=True)