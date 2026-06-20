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
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN)
subscribers = set()

# ================= AGGRESSIVE НАСТРОЙКИ =================
DATA_FILE = "config.json"
MODE = "aggressive"   # ← Изменено на aggressive

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        config = json.load(f)
        SYMBOLS = config.get("symbols", [])
        MODE = config.get("mode", "aggressive")
else:
    SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
        "TON/USDT", "AVAX/USDT", "SUI/USDT", "WIF/USDT", "PEPE/USDT",
        "BONK/USDT", "POPCAT/USDT", "SHIB/USDT"
    ]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 600  # проверка каждые 10 минут

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

Base.metadata.create_all(engine)

# ================= AGGRESSIVE СТРАТЕГИЯ =================
def get_signal(df, symbol):
    if len(df) < 60:
        return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])

    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    try:
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=2.5)
        df['supertrend'] = st['SUPERTd_10_2.5']
    except:
        df['supertrend'] = 0

    direction = None

    # Более агрессивные условия
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 48):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 52):
        direction = "SHORT"

    if not direction:
        return None

    atr = float(last.get('atr', price * 0.01))
    sl = round(price - atr * 1.5 if direction == "LONG" else price + atr * 1.5, 4)
    tp = round(price + atr * 3.0 if direction == "LONG" else price - atr * 3.0, 4)

    text = f"""
🚨 <b>AGGRESSIVE СИГНАЛ</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Цена: <b>{price:.4f}</b>
SL: <b>{sl}</b>
TP: <b>{tp}</b>
RSI: {last['rsi']:.1f}
Режим: AGGRESSIVE
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    try:
        session = Session()
        session.add(Signal(symbol=symbol, direction=direction, price=price))
        session.commit()
    except:
        pass

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 AGGRESSIVE режим запущен | Пар: {len(SYMBOLS)}")
    while True:
        for symbol in SYMBOLS:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
                df = pd.DataFrame