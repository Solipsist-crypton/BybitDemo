import pandas as pd
import pandas_ta as ta

# НАЛАШТУВАННЯ
HARD_STOP_PCT = 0.015  # 1.5% (стоп)
TAKE_PROFIT_PCT = 0.03 # 3.0% (тейк - співвідношення 1:2)
BREAK_EVEN_TRIGGER = 0.012 

def calculate_qty(symbol_price, target_usd=5, leverage=20):
    if symbol_price <= 0: return 0
    trade_value = target_usd * leverage
    qty = trade_value / symbol_price
    if symbol_price > 1000: return round(qty, 3)
    if symbol_price > 10: return round(qty, 2)
    return round(qty, 1)

def check_signals(df):
    if len(df) < 90: return "WAIT"
    # Використовуємо EMA 13, 34, 89
    ema13 = ta.ema(df['close'], length=13)
    ema34 = ta.ema(df['close'], length=34)
    ema89 = ta.ema(df['close'], length=89)
    last_price = df['close'].iloc[-1]
    
    if last_price > ema13.iloc[-1] > ema34.iloc[-1] > ema89.iloc[-1]:
        return "BUY"
    if last_price < ema13.iloc[-1] < ema34.iloc[-1] < ema89.iloc[-1]:
        return "SELL"
    return "WAIT"

def get_stop_loss_price(entry_price, side):
    return round(entry_price * (1 - HARD_STOP_PCT), 4) if side == "Buy" else round(entry_price * (1 + HARD_STOP_PCT), 4)

def get_take_profit_price(entry_price, side):
    return round(entry_price * (1 + TAKE_PROFIT_PCT), 4) if side == "Buy" else round(entry_price * (1 - TAKE_PROFIT_PCT), 4)

def check_break_even(entry_price, current_price, side):
    profit_pct = (current_price - entry_price) / entry_price
    if side == "Buy" and profit_pct >= BREAK_EVEN_TRIGGER: return True
    if side == "Sell" and profit_pct <= -BREAK_EVEN_TRIGGER: return True
    return False