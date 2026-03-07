import pandas as pd
import pandas_ta as ta

def check_signals(df):
    # Розрахунок твоїх трьох ліній EMA
    ema_fast = ta.ema(df['close'], length=13)
    ema_mid = ta.ema(df['close'], length=34)
    ema_slow = ta.ema(df['close'], length=89)

    if ema_fast is None or ema_mid is None or ema_slow is None:
        return "WAIT"

    # Останні значення
    last_fast = ema_fast.iloc[-1]
    last_mid = ema_mid.iloc[-1]
    last_slow = ema_slow.iloc[-1]
    
    # Попередні значення (для визначення моменту перетину)
    prev_fast = ema_fast.iloc[-2]
    prev_mid = ema_mid.iloc[-2]

    # Сигнал в LONG: 13 перетнула 34 знизу вгору + ціна вище 89
    if prev_fast <= prev_mid and last_fast > last_mid and df['close'].iloc[-1] > last_slow:
        return "BUY"
    
    # Сигнал в SHORT: 13 перетнула 34 зверху вниз + ціна нижче 89
    if prev_fast >= prev_mid and last_fast < last_mid and df['close'].iloc[-1] < last_slow:
        return "SELL"
        
    return "WAIT"

def calculate_trailing_stop(current_stop, current_price, side, callback_pct=0.01):
    """
    Автоматично підтягує стоп-лосс. 
    callback_pct=0.01 означає відступ у 1% від поточної ціни.
    """
    if side == "Buy":
        # Для лонгу новий стоп має бути вищим за старий
        new_stop = current_price * (1 - callback_pct)
        if current_stop == 0: return new_stop
        return max(current_stop, new_stop)
    else:
        # Для шорту новий стоп має бути нижчим за старий
        new_stop = current_price * (1 + callback_pct)
        if current_stop == 0: return new_stop
        return min(current_stop, new_stop)