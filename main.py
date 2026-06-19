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
DATA_FILE = "pairs.json"
MIN_VOLUME = 800000  # минимальный объём в долларах

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        SYMBOLS = json.load(f)
else:
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump(SYMBOLS, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 900

exchange = ccxt.binance({'enableRateLimit': True})

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

Base.metadata.create_all(engine)

# ================= ИНДИКАТОРЫ =================
def get_signal(df, symbol):
    if len(df) < 50 or df .iloc[-1 -1] < MIN_VOLUME:
        return None

    df = ta.ema(df , 9)
    df = ta.ema(df , 21)
    df = ta.rsi(df , 14)
    df = ta.atr(df , df , df['close