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
            rel_vol REAL,
            hour INTEGER,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

def log_trade(symbol, side, entry, exit, pnl, rel_vol=0):
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute('''
        INSERT INTO trades (symbol, side, entry_price, exit_price, pnl, rel_vol, hour, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, side, entry, exit, pnl, rel_vol, now.hour, now))
    conn.commit()
    conn.close()

def get_daily_pnl():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(pnl) FROM trades WHERE date(timestamp) = date('now')")
    res = cursor.fetchone()[0]
    conn.close()
    return res or 0

def get_stats_by_coin():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, SUM(pnl), COUNT(*) FROM trades GROUP BY symbol")
    res = cursor.fetchall()
    conn.close()
    return res

def get_stats_by_hour():
    conn = sqlite3.connect('trading_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT hour, SUM(pnl), COUNT(*) FROM trades GROUP BY hour ORDER BY hour")
    res = cursor.fetchall()
    conn.close()
    return res

def clear_db():
    try:
        conn = sqlite3.connect('trading_stats.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trades')
        conn.commit()
        conn.close()
        return True
    except: return False