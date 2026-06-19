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

# ================= НАСТРОЙКИ =================
DATA_FILE = "config.json"
MODE = "conservative"

# Инициализация SYMBOLS
SYMBOLS = []

if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r") as f:
            config = json.load(f)
            SYMBOLS = config.get("symbols", [])
            MODE = config.get("mode", "conservative")
    except:
        pass

# Если список пустой — заполняем по умолчанию
if not SYMBOLS:
    SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
        "TON/USDT", "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "SUI/USDT",
        "ADA/USDT", "BNB/USDT", "TRX/USDT", "PEPE/USDT", "WIF/USDT",
        "ARB/USDT", "OP/USDT", "HBAR/USDT", "KAS/USDT", "BONK/USDT",
        "POPCAT/USDT", "SHIB/USDT", "FLOKI/USDT", "BRETT/USDT", 
        "TIA/USDT", "SEI/USDT"
    ]
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

    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    try:
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        df['supertrend'] = st['SUPERTd_10_3.0']
    except:
        df['supertrend'] = 0

    last = df.iloc[-1]
    prev = df.iloc[-2]

    direction = None
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and 
        last['supertrend'] == 1 and last['rsi'] > 52):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and 
          last['supertrend'] == -1 and last['rsi'] < 48):
        direction = "SHORT"

    if not direction:
        return None

    if MODE == "conservative" and abs(last['rsi'] - 50) < 8:
        return None

    atr = float(last['atr']) if not pd.isna(last['atr']) else price * 0.012
    sl = round(price - atr * 1.8 if direction == "LONG" else price + atr * 1.8, 4)
    tp = round(price + atr * 3.6 if direction == "LONG" else price - atr * 3.6, 4)

    text = f"""
🚨 <b>BYBIT FUTURES СИГНАЛ</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Цена: <b>{price:.4f}</b>
SL: <b>{sl}</b>
TP: <b>{tp}</b>
RSI: {last['rsi']:.1f}
Режим: {MODE.upper()}
Время: {datetime.now().strftime("%d.%m %H:%M")}
    """.strip()

    try:
        session = Session()
        session.add(Signal(symbol=symbol, direction=direction, price=price, strategy="MULTI", mode=MODE))
        session.commit()
    except:
        pass

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 Бот запущен | Режим: {MODE} | Пар: {len(SYMBOLS)}")
    while True:
        for symbol in SYMBOLS:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=150)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                signal = get_signal(df, symbol)
                if signal:
                    for uid in list(subscribers):
                        try:
                            bot.send_message(uid, signal, parse_mode='HTML')
                        except:
                            subscribers.discard(uid)
            except:
                pass
            time.sleep(3)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Подписка активна! Хорошей прибыли 💰")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"🟢 Бот активен\nПодписчиков: {len(subscribers)}\nПары: {len(SYMBOLS)}\nРежим: {MODE.upper()}", parse_mode='HTML')

@bot.message_handler(commands=['pairs'])
def pairs(message):
    text = "📋 Активные пары:\n\n" + "\n".join(SYMBOLS)
    bot.reply_to(message, text)

@bot.message_handler(commands=['addpair'])
def addpair(message):
    if message.from_user.id != ADMIN_ID: 
        return bot.reply_to(message, "⛔ Только админ")
    try:
        pair = message.text.split()[1].upper()
        if '/' not in pair: pair += "/USDT"
        if pair not in SYMBOLS:
            SYMBOLS.append(pair)
            with open(DATA_FILE, "w") as f:
                json.dump({"symbols": SYMBOLS, "mode": MODE}, f)
            bot.reply_to(message, f"✅ Добавлена: {pair}")
    except:
        bot.reply_to(message, "Формат: /addpair POPCAT")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот успешно запущен!")
    bot.infinity_polling()