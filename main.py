import os
import time
import telebot
import pandas as pd
from pybit.unified_trading import HTTP
import strategy
from threading import Thread

# --- НАЛАШТУВАННЯ ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
QTY_LIST = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 1.0, "XRPUSDT": 100.0, "ADAUSDT": 100.0}

bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)

# Словник для відстеження активних позицій (щоб знати, коли вони зникнуть)
active_tracking = {}

def get_detailed_report():
    try:
        time.sleep(0.5)
        res = session.get_positions(category="linear", settleCoin="USDT")
        active = [p for p in res['result']['list'] if float(p['size']) > 0]
        
        if not active:
            return "📭 Активних позицій немає."
        
        report = "📊 *ПОТОЧНІ УГОДИ:*\n"
        total_pnl = 0
        for p in active:
            pnl = float(p['unrealisedPnl'])
            total_pnl += pnl
            report += f"🔹 *{p['symbol']}* | PnL: {pnl:.2f} USDT\n"
        report += f"\n💰 *ЗАГАЛЬНИЙ PnL: {total_pnl:.2f} USDT*"
        return report
    except Exception as e:
        return f"❌ Помилка: {e}"

@bot.callback_query_handler(func=lambda call: call.data == "refresh")
def callback_refresh(call):
    status_text = get_detailed_report()
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔄 Оновити статус", callback_data="refresh"))
    try:
        bot.edit_message_text(status_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    except:
        pass

def trading_loop():
    global active_tracking
    print("🚀 Бот почав роботу...")
    
    while True:
        try:
            # 1. Отримуємо поточні позиції
            res = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            current_active = {p['symbol']: p for p in res if float(p['size']) > 0}

            # 2. ПЕРЕВІРКА НА ЗАКРИТТЯ (було в active_tracking, але немає в current_active)
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    old_p = active_tracking[symbol]
                    # Отримуємо останню ціну для звіту
                    close_price = float(session.get_tickers(category="linear", symbol=symbol)['result']['list'][0]['lastPrice'])
                    pnl = float(old_p.get('unrealisedPnl', 0)) # Приблизний PnL на момент останнього скану
                    
                    msg = (f"🏁 *УГОДА ЗАКРИТА: {symbol}*\n"
                           f"💰 Приблизний PnL: {pnl:.2f} USDT\n"
                           f"🏁 Ціна виходу: {close_price}")
                    bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")
                    del active_tracking[symbol]

            # 3. ПЕРЕВІРКА СИГНАЛІВ ТА ВХІД
            for symbol in SYMBOLS:
                if symbol in current_active:
                    # Оновлюємо дані для трекінгу (для майбутнього закриття)
                    active_tracking[symbol] = current_active[symbol]
                    continue

                # Аналіз ринку
                kline = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(kline['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(QTY_LIST[symbol]))
                    bot.send_message(TG_CHAT_ID, f"🚀 *НОВИЙ ВХІД:* {symbol} | {side}", parse_mode="Markdown")

            # 4. УПРАВЛІННЯ TRAILING STOP
            for symbol, p in current_active.items():
                curr_sl = float(p['stopLoss']) if p['stopLoss'] else 0
                mark_price = float(p['markPrice'])
                new_sl = strategy.calculate_trailing_stop(curr_sl, mark_price, p['side'])
                
                if abs(new_sl - curr_sl) > (mark_price * 0.0005): # Зменшив поріг чутливості
                    session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(round(new_sl, 4)), slTriggerBy="MarkPrice")

        except Exception as e:
            print(f"Помилка: {e}")
            if "403" in str(e): time.sleep(300)
            
        time.sleep(60)

if __name__ == "__main__":
    Thread(target=trading_loop, daemon=True).start()
    bot.remove_webhook()
    
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔄 Оновити статус", callback_data="refresh"))
    bot.send_message(TG_CHAT_ID, "🤖 *Бот-Снайпер активований!*\nТепер я сповіщатиму про закриття угод.", reply_markup=markup, parse_mode="Markdown")
    bot.polling(none_stop=True)