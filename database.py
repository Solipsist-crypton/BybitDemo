import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            timestamp DATETIME,
            is_weekend INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def log_trade(symbol, side, entry, exit, pnl):
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    now = datetime.now()
    is_weekend = 1 if now.weekday() >= 5 else 0
    cursor.execute('''
        INSERT INTO trades (symbol, side, entry_price, exit_price, pnl, timestamp, is_weekend)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, side, entry, exit, pnl, now.strftime('%Y-%m-%d %H:%M:%S'), is_weekend))
    conn.commit()
    conn.close()

def get_stats_by_coin():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT symbol, SUM(pnl), COUNT(*) FROM trades GROUP BY symbol')
    data = cursor.fetchall()
    conn.close()
    return data

def get_daily_pnl():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(pnl) FROM trades WHERE timestamp >= date('now')")
    pnl = cursor.fetchone()[0]
    conn.close()
    return pnl or 0.0

def get_stats_by_hour():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    # strftime('%H', timestamp) витягує тільки годину з часу закриття угоди
    cursor.execute('''
        SELECT strftime('%H', timestamp) as hour, SUM(pnl), COUNT(*) 
        FROM trades 
        GROUP BY hour 
        ORDER BY hour ASC
    ''')
    data = cursor.fetchall()
    conn.close()
    return data