import pandas as pd

VOLUME_MULTIPLIER = 1.8
BREAKOUT_PERIOD = 5
STOP_LOSS_PCT = 0.015
TAKE_PROFIT_PCT = 0.03

def calculate_qty(symbol_price, target_usd=5, leverage=20):
    if symbol_price <= 0: return 0
    trade_value = target_usd * leverage
    qty = trade_value / symbol_price
    if symbol_price > 1000: return round(qty, 3)
    if symbol_price > 10: return round(qty, 2)
    return round(qty, 1)

def check_signals(df):
    if len(df) < 21: return "WAIT", 0
    
    # Середній об'єм (без поточної свічки)
    avg_vol = df['volume'].iloc[-21:-1].mean()
    curr_vol = df['volume'].iloc[-1]
    rel_vol = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 0
    
    # Умова сплеску
    is_vol_spike = curr_vol > (avg_vol * VOLUME_MULTIPLIER)
    
    # Локальні рівні
    prev_max = df['high'].iloc[-BREAKOUT_PERIOD-1:-1].max()
    prev_min = df['low'].iloc[-BREAKOUT_PERIOD-1:-1].min()
    curr_close = df['close'].iloc[-1]
    
    if is_vol_spike and curr_close > prev_max:
        return "BUY", rel_vol
    if is_vol_spike and curr_close < prev_min:
        return "SELL", rel_vol
        
    return "WAIT", 0

def get_stop_loss_price(price, side):
    return round(price * (1 - STOP_LOSS_PCT), 4) if side == "Buy" else round(price * (1 + STOP_LOSS_PCT), 4)

def get_take_profit_price(price, side):
    return round(price * (1 + TAKE_PROFIT_PCT), 4) if side == "Buy" else round(price * (1 - TAKE_PROFIT_PCT), 4)