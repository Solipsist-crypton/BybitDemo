import pandas as pd
import pandas_ta as ta

def check_signals(df):
    # Розрахунок твоїх трьох ліній
    ema_fast = ta.ema(df['close'], length=13)
    ema_mid = ta.ema(df['close'], length=34)
    ema_slow = ta.ema(df['close'], length=89)

    # Останні значення
    last_fast = ema_fast.iloc[-1]
    last_mid = ema_mid.iloc[-1]
    last_slow = ema_slow.iloc[-1]
    
    # Значення на попередній свічці (для визначення перетину)
    prev_fast = ema_fast.iloc[-2]
    prev_mid = ema_mid.iloc[-2]

    # Сигнал в LONG (13 перетинає 34 знизу вгору + ціна вище 89)
    if prev_fast <= prev_mid and last_fast > last_mid and df['close'].iloc[-1] > last_slow:
        return "BUY"
    
    # Сигнал в SHORT (13 перетинає 34 зверху вниз + ціна нижче 89)
    if prev_fast >= prev_mid and last_fast < last_mid and df['close'].iloc[-1] < last_slow:
        return "SELL"
        
    return "WAIT"