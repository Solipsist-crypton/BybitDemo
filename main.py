import os
import time
import telebot
import pandas as pd
from pybit.unified_trading import HTTP
from threading import Thread
import strategy
import database

# --- CONFIG ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COST_PER_TRADE = 5.0
LEVERAGE = 20
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)
database.init_db()

active_tracking = {}

def get_main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Баланс", "📊 Поточні угоди")
    markup.add("📈 Статистика монет", "📅 Денний звіт")
    markup.add("⚠️ PANIC SELL")
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(TG_CHAT_ID, "🚀 Снайпер активований. Ризик: 5$ | Плече: 20x", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if message.text == "💰 Баланс":
        try:
            res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if res['result']['list'] and res['result']['list'][0].get('coin'):
                data = res['result']['list'][0]['coin'][0]
                msg = (f"💵 *Гаманець:* {float(data['walletBalance']):.2f} USDT\n"
                       f"✅ *Доступно:* {float(data['availableToWithdraw']):.2f} USDT\n"
                       f"📉 *Equity:* {float(data['equity']):.2f} USDT")
            else:
                msg = "❌ Не вдалося отримати баланс. Перевір налаштування Demo-рахунку."
            bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(TG_CHAT_ID, f"❌ Помилка API: {e}")

    elif message.text == "📊 Поточні угоди":
        try:
            res = session.get_positions(category="linear", settleCoin="USDT")
            active = [p for p in res['result']['list'] if float(p['size']) > 0]
            if not active:
                bot.send_message(TG_CHAT_ID, "📭 Немає відкритих позицій.")
                return
            for p in active:
                pnl = float(p['unrealisedPnl'])
                roi = (pnl / COST_PER_TRADE) * 100
                bot.send_message(TG_CHAT_ID, 
                    f"🔹 *{p['symbol']}* ({p['side']})\n"
                    f"ROI: {roi:.2f}% | PnL: {pnl:.2f} USDT\n"
                    f"Вхід: {p['avgPrice']} | Ціна: {p['markPrice']}", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(TG_CHAT_ID, f"❌ Помилка: {e}")

    elif message.text == "📈 Статистика монет":
        stats = database.get_stats_by_coin()
        if not stats:
            bot.send_message(TG_CHAT_ID, "📈 Історія порожня. Чекаю перших закритих угод.")
            return
        msg = "📊 *Прибуток по монетах:*\n"
        for row in stats:
            msg += f"• {row[0]}: {row[1]:.2f} USDT ({row[2]} угод)\n"
        bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "📅 Денний звіт":
        pnl = database.get_daily_pnl()
        bot.send_message(TG_CHAT_ID, f"📅 *PnL за сьогодні:* {pnl:.2f} USDT", parse_mode="Markdown")

    elif message.text == "⚠️ PANIC SELL":
        try:
            res = session.get_positions(category="linear", settleCoin="USDT")
            for p in res['result']['list']:
                if float(p['size']) > 0:
                    side = "Sell" if p['side'] == "Buy" else "Buy"
                    session.place_order(category="linear", symbol=p['symbol'], side=side, orderType="Market", qty=p['size'])
            bot.send_message(TG_CHAT_ID, "🛑 ВСІ УГОДИ ЗАКРИТО!", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.send_message(TG_CHAT_ID, f"❌ Помилка при закритті: {e}")

def trading_loop():
    global active_tracking
    print("🚀 Цикл торгівлі запущено...")
    while True:
        try:
            # Отримуємо позиції
            pos_res = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            current_active = {p['symbol']: p for p in pos_res if float(p['size']) > 0}

            # 1. ПЕРЕВІРКА ЗАКРИТТЯ
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    time.sleep(3) # Час для оновлення історії Bybit
                    closed = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)['result']['list']
                    if closed:
                        c = closed[0]
                        f_pnl = float(c['closedPnl'])
                        database.log_trade(symbol, c['side'], c['avgEntryPrice'], c['avgExitPrice'], f_pnl)
                        emoji = "✅" if f_pnl > 0 else "❌"
                        bot.send_message(TG_CHAT_ID, f"{emoji} *ЗАКРИТО {symbol}*\nPnL: {f_pnl:.4f} USDT", parse_mode="Markdown")
                    del active_tracking[symbol]

            # 2. МОНІТОРИНГ ТА АНАЛІЗ
            for symbol in SYMBOLS:
                if symbol in current_active:
                    p = current_active[symbol]
                    active_tracking[symbol] = p
                    
                    # Логіка безубитку через strategy.py
                    entry = float(p['avgPrice'])
                    mark = float(p['markPrice'])
                    curr_sl = float(p['stopLoss']) if p['stopLoss'] else 0
                    
                    if curr_sl != entry:
                        if strategy.check_break_even(entry, mark, p['side']):
                            session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(entry), slTriggerBy="MarkPrice")
                            bot.send_message(TG_CHAT_ID, f"🛡 *{symbol}* в безубитку (Entry: {entry})")
                    continue

                # Отримуємо дані свічок
                kline = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(kline['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                # ВИПРАВЛЕНО: Визначаємо сигнал перед використанням
                signal = strategy.check_signals(df)
                
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    tickers = session.get_tickers(category="linear", symbol=symbol)
                    price = float(tickers['result']['list'][0]['lastPrice'])
                    
                    qty = strategy.calculate_qty(price, COST_PER_TRADE, LEVERAGE)
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(qty))
                    bot.send_message(TG_CHAT_ID, f"🚀 *ВХІД {symbol}* | {side} | Лот: {qty}")

        except Exception as e:
            print(f"Loop Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    # Вбиваємо старий вебхук, щоб уникнути конфлікту 409
    bot.remove_webhook()
    time.sleep(1)
    
    # Запуск торгового потоку
    t = Thread(target=trading_loop, daemon=True)
    t.start()
    
    # Запуск Telegram бота
    print("🤖 Бот чекає повідомлень...")
    bot.polling(none_stop=True)