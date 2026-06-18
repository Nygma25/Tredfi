import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime

# =========================
# CONNECT MT5
# =========================
def connect():
    if not mt5.initialize():
        print("❌ MT5 connection failed")
        quit()
    print("✅ MT5 connected")


# =========================
# DATA
# =========================
def get_data(symbol, tf, n=200):
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    df = pd.DataFrame(rates)
    return df


# =========================
# STRUCTURE
# =========================
def trend(df):
    ema50 = df["close"].ewm(span=50).mean()
    ema200 = df["close"].ewm(span=200).mean()

    if ema50.iloc[-1] > ema200.iloc[-1]:
        return "BULL"
    if ema50.iloc[-1] < ema200.iloc[-1]:
        return "BEAR"
    return "RANGE"


# =========================
# LIQUIDITY SWEEP
# =========================
def liquidity(df):
    if df["low"].iloc[-1] < df["low"].rolling(20).min().iloc[-2]:
        return "SWEEP_LOW"
    if df["high"].iloc[-1] > df["high"].rolling(20).max().iloc[-2]:
        return "SWEEP_HIGH"
    return None


# =========================
# ORDER BLOCK FILTER
# =========================
def order_block(df):
    body = abs(df["close"] - df["open"])
    idx = body.idxmax()

    low = df.loc[idx, "low"]
    high = df.loc[idx, "high"]

    price = df["close"].iloc[-1]

    return low <= price <= high


# =========================
# SESSION FILTER
# =========================
def session_ok():
    hour = datetime.utcnow().hour
    return (7 <= hour <= 11) or (13 <= hour <= 17)


# =========================
# SCORE SYSTEM
# =========================
def score(htf, sweep, ob, session):

    s = 0

    if htf in ["BULL", "BEAR"]:
        s += 3
    if sweep:
        s += 3
    if ob:
        s += 2
    if session:
        s += 2

    return s


# =========================
# RISK MANAGER
# =========================
class Risk:
    def __init__(self):
        self.balance = 10000
        self.daily_loss = 0
        self.trades = 0

    def allow(self):
        if self.daily_loss >= self.balance * 0.05:
            return False
        if self.trades >= 3:
            return False
        return True

    def update(self, pnl):
        self.trades += 1
        self.balance += pnl

        if pnl < 0:
            self.daily_loss += abs(pnl)


# =========================
# ORDER EXECUTION
# =========================
def send_order(symbol, action, lot):

    tick = mt5.symbol_info_tick(symbol)

    price = tick.ask if action == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": 20,
        "magic": 12345,
        "comment": "PROP BOT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    return mt5.order_send(request)


# =========================
# LOT SIZE
# =========================
def lot(balance):
    return round(balance * 0.01 / 1000, 2)


# =========================
# MAIN LOOP
# =========================
def run():

    connect()

    symbol = "BTCUSD"
    tf = mt5.TIMEFRAME_M15

    risk = Risk()

    while True:

        if not risk.allow():
            print("⛔ Risk limit reached")
            time.sleep(60)
            continue

        df = get_data(symbol, tf)

        htf = trend(df)
        sweep = liquidity(df)
        ob = order_block(df)
        session = session_ok()

        sc = score(htf, sweep, ob, session)

        if sc >= 8:

            action = "BUY" if htf == "BULL" else "SELL"

            pnl = 100  # placeholder (later real tracking)

            risk.update(pnl)

            send_order(symbol, action, lot(risk.balance))

            print(f"""
🚨 TRADE EXECUTED
📊 {action}
🧠 SCORE: {sc}
💰 BALANCE: {risk.balance}
📉 DD: {risk.daily_loss}
""")

        time.sleep(60)


run()