import telebot
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import threading
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN)
subscribers = set()

# ================= НАСТРОЙКИ =================
DATA_FILE = "config.json"
MODE = "conservative"  # conservative / aggressive

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        config = json.load(f)
        SYMBOLS = config.get("symbols", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
        MODE = config.get("mode", "conservative")
else:
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 900

exchange = ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'future'}})

# База данных
Base = declarative_base()
engine = create_engine('sqlite:///signals.db', echo=False)
Session = sessionmaker(bind=engine)

class Signal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String)
    direction = Column(String)
    price = Column(Float)
    strategy = Column(String)
    mode = Column(String)

Base.metadata.create_all(engine)

# ================= СТРАТЕГИЯ =================
def get_signal(df, symbol):
    if len(df) < 80:
        return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    volume = float(last['volume'])

    # Индикаторы
    df['ema9'] = ta.ema(df['close'], 9)
    df['ema21'] = ta.ema(df['close'], 21)
    df['rsi'] = ta.rsi(df['close'], 14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], 14)
    df['supertrend'] = ta.supertrend(df['high'], df['low'], df['close'], 10, 3)['SUPERTd_10_3.0']

    last = df.iloc[-1]
    prev = df.iloc[-2]

    direction = None
    strategy = "MULTI"

    # Основное условие
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and 
        last['supertrend'] == 1 and last['rsi'] > 52):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and 
          last['supertrend'] == -1 and last['rsi'] < 48):
        direction = "SHORT"

    if not direction:
        return None

    # Фильтр агрессивности
    if MODE == "conservative" and abs(last['rsi'] - 50) < 8:
        return None

    atr = float(last['atr']) if not pd.isna(last['atr']) else price * 0.012
    sl = round(price - atr * 1.8 if direction == "LONG" else price + atr * 1.8, 4)
    tp = round(price + atr * 3.6 if direction == "LONG" else price - atr * 3.6, 4)

    text = f"""
🚨 <b>BYBIT FUTURES</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Стратегия: {