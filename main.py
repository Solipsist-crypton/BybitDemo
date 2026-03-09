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
        res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        data = res['result']['list'][0]['coin'][0]
        msg = (f"💵 *Гаманець:* {float(data['walletBalance']):.2f} USDT\n"
               f"✅ *Доступно:* {float(data['availableToWithdraw']):.2f} USDT\n"
               f"📉 *Equity:* {float(data['equity']):.2f} USDT")
        bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "📊 Поточні угоди":
        res = session.get_positions(category="linear", settleCoin="USDT")
        active = [p for p in res['result']['list'] if float(p['size']) > 0]
        if not active:
            bot.send_message(TG_CHAT_ID, "📭 Немає відкритих позицій.")
            return
        for p in active:
            roi = (float(p['unrealisedPnl']) / COST_PER_TRADE) * 100
            msg = (f"🔹 *{p['symbol']}* ({p['side']})\n"
                   f"ROI: {roi:.2f}% | PnL: {p['unrealisedPnl']} USDT\n"
                   f"Вхід: {p['avgPrice']} | Ціна: {p['markPrice']}")
            bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "📈 Статистика монет":
        stats = database.get_stats_by_coin()
        msg = "📊 *Прибуток по монетах:*\n"
        for row in stats:
            msg += f"{row[0]}: {row[1]:.2f} USDT ({row[2]} угод)\n"
        bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "📅 Денний звіт":
        pnl = database.get_daily_pnl()
        bot.send_message(TG_CHAT_ID, f"📅 *PnL за сьогодні:* {pnl:.2f} USDT")

    elif message.text == "⚠️ PANIC SELL":
        res = session.get_positions(category="linear", settleCoin="USDT")
        for p in res['result']['list']:
            if float(p['size']) > 0:
                side = "Sell" if p['side'] == "Buy" else "Buy"
                session.place_order(category="linear", symbol=p['symbol'], side=side, orderType="Market", qty=p['size'])
        bot.send_message(TG_CHAT_ID, "🛑 ВСІ УГОДИ ЗАКРИТО!")

def trading_loop():
    global active_tracking
    while True:
        try:
            res = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            current_active = {p['symbol']: p for p in res if float(p['size']) > 0}

            # 1. ПЕРЕВІРКА ЗАКРИТТЯ
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    time.sleep(2)
                    closed = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)['result']['list']
                    if closed:
                        c = closed[0]
                        database.log_trade(symbol, c['side'], c['avgEntryPrice'], c['avgExitPrice'], float(c['closedPnl']))
                        emoji = "✅" if float(c['closedPnl']) > 0 else "❌"
                        bot.send_message(TG_CHAT_ID, f"{emoji} *ЗАКРИТО {symbol}*\nPnL: {c['closedPnl']} USDT")
                    del active_tracking[symbol]

            # 2. МОНІТОРИНГ РИНКУ
            for symbol in SYMBOLS:
                if symbol in current_active:
                    p = current_active[symbol]
                    active_tracking[symbol] = p
                    # Логіка БЕЗУБИТКУ
                    if float(p['stopLoss']) != float(p['avgPrice']):
                        if strategy.check_break_even(float(p['avgPrice']), float(p['markPrice']), p['side']):
                            session.set_trading_stop(category="linear", symbol=symbol, stopLoss=p['avgPrice'], slTriggerBy="MarkPrice")
                            bot.send_message(TG_CHAT_ID, f"🛡 *{symbol}* переведено в безубиток!")
                    continue

                # ВХІД В УГОДУ
                kline = session.get_kline(category="linear", symbol=symbol, interval="5", limit=50)
                df = pd.DataFrame(kline['result']['list']) # Додай обробку як раніше
                # ... аналіз сигналу ...
                if signal != "WAIT":
                    price = float(session.get_tickers(category="linear", symbol=symbol)['result']['list'][0]['lastPrice'])
                    qty = strategy.calculate_qty(price, COST_PER_TRADE, LEVERAGE)
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(qty))
                    bot.send_message(TG_CHAT_ID, f"🚀 *ВХІД {symbol}* на 5$ (x20)")

        except Exception as e:
            print(f"Loop Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    Thread(target=trading_loop, daemon=True).start()
    bot.polling(none_stop=True)