import os
import time
from datetime import datetime, timedelta
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
MAX_TIME_MINUTES = 45 # Закриваємо, якщо довго "жує"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

bot = telebot.TeleBot(TG_TOKEN)
session = HTTP(testnet=False, demo=True, api_key=API_KEY, api_secret=API_SECRET)
database.init_db()

active_tracking = {} # Зберігаємо час входу: {symbol: {'start_time': dt, 'side': s}}

def get_main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Баланс", "📊 Поточні угоди")
    markup.add("📈 Статистика монет", "📅 Денний звіт")
    markup.add("⚠️ PANIC SELL")
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(TG_CHAT_ID, "🛡 Бот-Снайпер активований. Захист: Hard Stop 1.5% + Time-out.", reply_markup=get_main_keyboard())

# ... блоки Баланс, Статистика залишаються без змін ...
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if message.text == "💰 Баланс":
        try:
            res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            data = res['result']['list'][0]['coin'][0]
            w_bal = float(data.get('walletBalance', 0) or 0)
            eq = float(data.get('equity', 0) or 0)
            bot.send_message(TG_CHAT_ID, f"💵 *Wallet:* {w_bal:.2f}\n📉 *Equity:* {eq:.2f}", parse_mode="Markdown")
        except: bot.send_message(TG_CHAT_ID, "Помилка балансу")
    
    elif message.text == "📊 Поточні угоди":
        res = session.get_positions(category="linear", settleCoin="USDT")
        active = [p for p in res['result']['list'] if float(p['size'] or 0) > 0]
        if not active: bot.send_message(TG_CHAT_ID, "📭 Порожньо"); return
        for p in active:
            bot.send_message(TG_CHAT_ID, f"🔹 *{p['symbol']}* | PnL: {p['unrealisedPnl']} USDT", parse_mode="Markdown")

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

            # 1. ОБРОБКА ЗАКРИТТЯ ТА ТАЙМ-АУТУ
            for symbol in list(active_tracking.keys()):
                if symbol not in current_active:
                    time.sleep(3)
                    closed = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)['result']['list']
                    if closed:
                        c = closed[0]
                        database.log_trade(symbol, c['side'], c['avgEntryPrice'], c['avgExitPrice'], float(c['closedPnl'] or 0))
                        bot.send_message(TG_CHAT_ID, f"🏁 *ЗАКРИТО {symbol}* | PnL: {c['closedPnl']}")
                    del active_tracking[symbol]
                    continue
                
                # Перевірка на "зависання" угоди (Time-out)
                start_time = active_tracking[symbol].get('time')
                if start_time and datetime.now() > start_time + timedelta(minutes=MAX_TIME_MINUTES):
                    p = current_active[symbol]
                    side = "Sell" if p['side'] == "Buy" else "Buy"
                    session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=p['size'])
                    bot.send_message(TG_CHAT_ID, f"⏰ *ТАЙМ-АУТ:* Закрито {symbol} через довге очікування.")

            # 2. МОНІТОРИНГ ТА ВХІД
            for symbol in SYMBOLS:
                if symbol in current_active:
                    p = current_active[symbol]
                    # Оновлюємо tracking
                    if symbol not in active_tracking: 
                        active_tracking[symbol] = {'time': datetime.now()}
                    
                    # Логіка безубитку
                    entry = float(p['avgPrice'] or 0)
                    mark = float(p['markPrice'] or 0)
                    sl = float(p['stopLoss'] or 0)
                    if entry > 0 and sl != entry:
                        if strategy.check_break_even(entry, mark, p['side']):
                            session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(entry), slTriggerBy="MarkPrice")
                            bot.send_message(TG_CHAT_ID, f"🛡 *{symbol}* -> Безубиток.")
                    continue

                # Сигнал на вхід
                kline = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
                df = pd.DataFrame(kline['result']['list'], columns=['time','open','high','low','close','volume','turnover'])
                df['close'] = df['close'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)

                signal = strategy.check_signals(df)
                if signal != "WAIT":
                    side = "Buy" if signal == "BUY" else "Sell"
                    price = float(session.get_tickers(category="linear", symbol=symbol)['result']['list'][0]['lastPrice'])
                    qty = strategy.calculate_qty(price, COST_PER_TRADE, LEVERAGE)
                    sl_price = strategy.get_stop_loss_price(price, side)
                    
                    # Відкриваємо угоду ОДРАЗУ зі СТОП-ЛОССОМ
                    session.place_order(
                        category="linear", symbol=symbol, side=side, orderType="Market", 
                        qty=str(qty), stopLoss=str(sl_price), slTriggerBy="MarkPrice"
                    )
                    active_tracking[symbol] = {'time': datetime.now()}
                    bot.send_message(TG_CHAT_ID, f"🚀 *ВХІД {symbol}*\nЛот: {qty}\n🛡 Stop Loss: {sl_price}")

        except Exception as e: print(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    bot.remove_webhook()
    Thread(target=trading_loop, daemon=True).start()
    bot.polling(none_stop=True)