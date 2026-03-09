import pandas as pd
import pandas_ta as ta

def calculate_qty(symbol_price, target_usd=5, leverage=20):
    """
    Рахує кількість монет (Qty) для входу на фіксовану суму маржі.
    Формула: (Сума в USD * Плече) / Ціна монети
    """
    if symbol_price <= 0:
        return 0
    
    trade_value = target_usd * leverage
    qty = trade_value / symbol_price
    
    # Округлення qty залежно від ціни (крок лота)
    # Для BTC/ETH зазвичай 3 знаки, для XRP/ADA — 1 або 0
    if symbol_price > 1000:
        return round(qty, 3)
    elif symbol_price > 10:
        return round(qty, 2)
    else:
        return round(qty, 1)

def check_signals(df):
    """
    Стратегія на основі трьох EMA (13, 34, 89)
    """
    if len(df) < 90:
        return "WAIT"

    ema13 = ta.ema(df['close'], length=13)
    ema34 = ta.ema(df['close'], length=34)
    ema89 = ta.ema(df['close'], length=89)

    last_price = df['close'].iloc[-1]
    
    # Логіка LONG: ціна > EMA13 > EMA34 > EMA89
    if last_price > ema13.iloc[-1] > ema34.iloc[-1] > ema89.iloc[-1]:
        return "BUY"
    
    # Логіка SHORT: ціна < EMA13 < EMA34 < EMA89
    if last_price < ema13.iloc[-1] < ema34.iloc[-1] < ema89.iloc[-1]:
        return "SELL"
    
    return "WAIT"

def calculate_trailing_stop(current_sl, current_price, side, callback_rate=0.01):
    """
    Розрахунок трейлінг-стопу (1% від ціни)
    """
    if side == "Buy":
        new_sl = current_price * (1 - callback_rate)
        return max(current_sl, new_sl) if current_sl > 0 else new_sl
    else:
        new_sl = current_price * (1 + callback_rate)
        return min(current_sl, new_sl) if current_sl > 0 else new_sl

def check_break_even(entry_price, current_price, side, trigger_pct=0.012):
    """
    Перевіряє, чи пройшла ціна +1.2%, щоб переставити стоп у безубиток.
    """
    profit_pct = (current_price - entry_price) / entry_price
    
    if side == "Buy" and profit_pct >= trigger_pct:
        return True
    if side == "Sell" and profit_pct <= -trigger_pct:
        return True
    return False