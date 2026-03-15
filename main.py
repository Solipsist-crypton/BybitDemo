import os
import time
from datetime import datetime
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
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", 
           "DOTUSDT", "MATICUSDT", "LTCUSDT", "AVAXUSDT", "LINKUSDT"]

bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)
database.init_db()

active_tracking = {}

def get_main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Баланс", "📊 Поточні угоди")
    markup.add("📈 Статистика монет", "📅 Денний звіт")
    markup.add("🕒 Статистика по часам", "⚠️ PANIC SELL")
    markup.add("🧹 Очистити статистику", "📤 Експорт бази")
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(TG_CHAT_ID, "🚀 Снайпер об'ємів M15 активований.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if message.text == "💰 Баланс":
        try:
            res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            data = res['result']['list'][0]['coin'][0]
            bot.send_message(TG_CHAT_ID, f"💵 *Wallet:* {data['walletBalance']}\n📉 *Equity:* {data['equity']}", parse_mode="Markdown")
        except: bot.send_message(TG_CHAT_ID, "Помилка балансу")
    
    elif message.text == "📊 Поточні угоди":
        res = session.get_positions(category="linear", settleCoin="USDT")
        active = [p for p in res['result']['list'] if float(p['size'] or 0) > 0]
        if not active: bot.send_message(TG_CHAT_ID, "📭 Порожньо"); return
        for p in active:
            bot.send_message(TG_CHAT_ID, f"🔹 *{p['symbol']}* | PnL: {p['unrealisedPnl']} USDT", parse_mode="Markdown")

    elif message.text == "📈 Статистика монет":
        stats = database.get_stats_by_coin()
        if not stats: bot.send_message(TG_CHAT_ID, "📊 Порожньо"); return
        msg = "📈 *Прибуток по монетах:*\n" + "\n".join([f"• {r[0]}: {r[1]:.2f} USDT ({r[2]})" for r in stats])
        bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "🕒 Статистика по часам":
        h_stats = database.get_stats_by_hour()
        if not h_stats: bot.send_message(TG_CHAT_ID, "🕒 Порожньо"); return
        msg = "🕒 *Прибуток по годинах (UTC):*\n" + "\n".join([f"{'🟢' if r[1]>0 else '🔴'} {r[0]}:00 — {r[1]:.2f} USDT" for r in h_stats])
        bot.send_message(TG_CHAT_ID, msg, parse_mode="Markdown")

    elif message.text == "📅 Денний звіт":
        pnl = database.get_daily_pnl()
        bot.send_message(TG_CHAT_ID, f"📅 *PnL за сьогодні:* {pnl:.2f} USDT", parse_mode="Markdown")

    elif message.text == "🧹 Очистити статистику":
        if database.clear_db(): bot.send_message(TG_CHAT_ID, "🧹 База очищена.")
        
    elif message.text == "📤 Експорт бази":
        try:
            with open('trading_stats.db', 'rb') as f:
                bot.send_document(TG_CHAT_ID, f, caption="📂 Файл бази даних для аналізу.")
        except: bot.send_message(TG_CHAT_ID, "Помилка при експорті.")

    elif message.text == "⚠️ PANIC SELL":
        res = session.get_positions(category="linear", settleCoin="USDT")
        for p in res['result']['list']:
            if float(p['size'] or 0) > 0:
                side = "Sell" if p['side'] == "Buy" else "Buy"
                session.place_order(category="linear", symbol=p['symbol'], side=side, orderType="Market", qty=p['size'])
        bot.send_message(TG_CHAT_ID, "🛑 ВСЕ ЗАКРИТО")

def trading_loop():
    global active_tracking
    while True:
        try:
            pos_res = session.get_positions(category="linear", settleCoin="USDT")['result']['list']
            current_active = {p['symbol']: p for p in pos_res if float(p['size'] or 0) > 0}

            # 1. ОБРОБКА ЗАКРИТТЯ
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    time.sleep(5)
                    closed = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)['result']['list']
                    if closed:
                        c = closed[0]
                        rv = active_tracking[symbol].get('rel_vol', 0)
                        database.log_trade(symbol, c['side'], c['avgEntryPrice'], c['avgExitPrice'], float(c['closedPnl'] or 0), rv)
                        bot.send_message(TG_CHAT_ID, f"🏁 *ЗАКРИТО {symbol}* | PnL: {c['closedPnl']}")
                    del active_tracking[symbol]

            # 2. МОНІТОРИНГ ТА ВХІД
            for symbol in SYMBOLS:
                if symbol in current_active:
                    if symbol not in active_tracking: active_tracking[symbol] = {'time': datetime.now()}
                    continue

                kline = session.get_kline(category="linear", symbol=symbol, interval="15", limit=50)
                df = pd.DataFrame(kline['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                signal, rel_vol = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    price = float(session.get_tickers(category="linear", symbol=symbol)['result']['list'][0]['lastPrice'])
                    qty = strategy.calculate_qty(price, COST_PER_TRADE, LEVERAGE)
                    sl = strategy.get_stop_loss_price(price, side)
                    tp = strategy.get_take_profit_price(price, side)
                    
                    session.place_order(
                        category="linear", symbol=symbol, side=side, orderType="Market", 
                        qty=str(qty), stopLoss=str(sl), takeProfit=str(tp)
                    )
                    active_tracking[symbol] = {'time': datetime.now(), 'rel_vol': rel_vol}
                    bot.send_message(TG_CHAT_ID, f"🚀 *ВХІД {symbol}* (Vol x{rel_vol})\n🎯 TP: {tp}\n🛡 SL: {sl}")

        except Exception as e: print(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    bot.remove_webhook()
    Thread(target=trading_loop, daemon=True).start()
    bot.polling(none_stop=True)