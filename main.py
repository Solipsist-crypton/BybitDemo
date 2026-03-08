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

active_tracking = {}

def get_detailed_report():
    try:
        res = session.get_positions(category="linear", settleCoin="USDT")
        active = [p for p in res['result']['list'] if float(p['size']) > 0]
        if not active: return "📭 Активних позицій немає."
        
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
    except: pass

def trading_loop():
    global active_tracking
    print("🚀 Бот у роботі. Регіон: Нідерланди. Моніторинг закриття увімкнено.")
    
    while True:
        try:
            # 1. Отримуємо поточні позиції
            res = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            current_active = {p['symbol']: p for p in res if float(p['size']) > 0}

            # 2. ПЕРЕВІРКА НА ЗАКРИТТЯ (Реальний PnL з історії)
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    time.sleep(2) # Даємо біржі час оновити історію
                    closed_res = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
                    
                    if closed_res['result']['list']:
                        trade = closed_res['result']['list'][0]
                        f_pnl = float(trade['closedPnl'])
                        f_exit = float(trade['avgExitPrice'])
                        f_entry = float(trade['avgEntryPrice'])
                        
                        emoji = "✅ ПРОФІТ" if f_pnl > 0 else "❌ СТОП-ЛОСС"
                        msg = (f"{emoji}: *{symbol}*\n"
                               f"📈 Вхід: {f_entry:.4f}\n"
                               f"📉 Вихід: {f_exit:.4f}\n"
                               f"💰 *Чистий PnL: {f_pnl:.4f} USDT* (з комісією)")
                    else:
                        msg = f"🏁 *{symbol} закрита* (дані в обробці...)"
                    
                    bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")
                    del active_tracking[symbol]

            # 3. АНАЛІЗ ТА ВХІД
            for symbol in SYMBOLS:
                if symbol in current_active:
                    active_tracking[symbol] = current_active[symbol]
                    continue

                kline = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(kline['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(QTY_LIST[symbol]))
                    bot.send_message(TG_CHAT_ID, f"🚀 *НОВИЙ ВХІД:* {symbol} | {side}", parse_mode="Markdown")

            # 4. TRAILING STOP
            for symbol, p in current_active.items():
                curr_sl = float(p['stopLoss']) if p['stopLoss'] else 0
                new_sl = strategy.calculate_trailing_stop(curr_sl, float(p['markPrice']), p['side'])
                if abs(new_sl - curr_sl) > (float(p['markPrice']) * 0.0005):
                    session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(round(new_sl, 4)), slTriggerBy="MarkPrice")

        except Exception as e:
            print(f"Error: {e}")
            if "403" in str(e): time.sleep(300)
        time.sleep(60)

if __name__ == "__main__":
    Thread(target=trading_loop, daemon=True).start()
    bot.remove_webhook()
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔄 Оновити статус", callback_data="refresh"))
    bot.send_message(TG_CHAT_ID, "🤖 *Снайпер оновлений!*\nТепер показую реальний PnL з урахуванням комісій.", reply_markup=markup, parse_mode="Markdown")
    bot.polling(none_stop=True)