import pandas as pd
import numpy as np

# --- НАЛАШТУВАННЯ ---
BASE_VOLUME_MULTIPLIER = 1.8
BREAKOUT_PERIOD = 5
STOP_LOSS_PCT = 0.015
TAKE_PROFIT_PCT = 0.03
MIN_BODY_RATIO = 0.4  # Тіло свічки має бути > 40% від усього діапазону (High-Low)

def calculate_qty(symbol_price, target_usd=5, leverage=20):
    if symbol_price <= 0: return 0
    trade_value = target_usd * leverage
    qty = trade_value / symbol_price
    if symbol_price > 1000: return round(qty, 3)
    if symbol_price > 10: return round(qty, 2)
    return round(qty, 1)

def get_adaptive_threshold(df):
    """Підвищує поріг об'єму, якщо волатильність низька (наприклад, вихідні)"""
    recent_atr = (df['high'].iloc[-10:] - df['low'].iloc[-10:]).mean()
    prev_atr = (df['high'].iloc[-20:-10] - df['low'].iloc[-20:-10]).mean()
    
    if recent_atr < prev_atr * 0.8: # Ринок затухає
        return BASE_VOLUME_MULTIPLIER * 1.25 # Піднімаємо поріг на 25%
    return BASE_VOLUME_MULTIPLIER

def check_signals(df):
    if len(df) < 21: return "WAIT", 0
    
    # 1. Адаптивний поріг об'єму
    dynamic_multiplier = get_adaptive_threshold(df)
    avg_vol = df['volume'].iloc[-21:-1].mean()
    curr_vol = df['volume'].iloc[-1]
    rel_vol = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 0
    
    # 2. Перевірка якості свічки (Effort vs Result)
    candle_range = df['high'].iloc[-1] - df['low'].iloc[-1]
    body_size = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
    is_good_quality = (body_size / candle_range) > MIN_BODY_RATIO if candle_range > 0 else False

    # 3. Умови пробою
    prev_max = df['high'].iloc[-BREAKOUT_PERIOD-1:-1].max()
    prev_min = df['low'].iloc[-BREAKOUT_PERIOD-1:-1].min()
    curr_close = df['close'].iloc[-1]
    
    # Сигнал Long
    if rel_vol > dynamic_multiplier and curr_close > prev_max and is_good_quality:
        return "BUY", rel_vol
    
    # Сигнал Short
    if rel_vol > dynamic_multiplier and curr_close < prev_min and is_good_quality:
        return "SELL", rel_vol
        
    return "WAIT", 0

def check_exit_signals(df, entry_side, entry_rel_vol):
    """Перевірка на зустрічний сильний імпульс"""
    curr_vol = df['volume'].iloc[-1]
    avg_vol = df['volume'].iloc[-21:-1].mean()
    curr_rel_vol = curr_vol / avg_vol if avg_vol > 0 else 0
    
    curr_close = df['close'].iloc[-1]
    curr_open = df['open'].iloc[-1]
    
    # Якщо ми в Long, а з'явився аномальний Short-об'єм
    if entry_side == "Buy" and curr_close < curr_open and curr_rel_vol > entry_rel_vol:
        return True # Тікаємо!
        
    # Якщо ми в Short, а з'явився аномальний Long-об'єм
    if entry_side == "Sell" and curr_close > curr_open and curr_rel_vol > entry_rel_vol:
        return True # Тікаємо!
        
    return False

def get_stop_loss_price(price, side):
    return round(price * (1 - STOP_LOSS_PCT), 4) if side == "Buy" else round(price * (1 + STOP_LOSS_PCT), 4)

def get_take_profit_price(price, side):
    return round(price * (1 + TAKE_PROFIT_PCT), 4) if side == "Buy" else round(price * (1 - TAKE_PROFIT_PCT), 4)