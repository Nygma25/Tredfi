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
MODE = "aggressive"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        config = json.load(f)
        SYMBOLS = config.get("symbols", [])
        MODE = config.get("mode", "aggressive")
else:
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "SUI/USDT", "WIF/USDT", "PEPE/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 600

exchange = ccxt.okx({'enableRateLimit': True})

# База данных для статистики
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

# ================= СТРАТЕГИЯ =================
def get_signal(df, symbol):
    if len(df) < 50:
        return None
    
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])

    direction = None
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 45):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 55):
        direction = "SHORT"

    if not direction:
        return None

    text = f"""
🚨 <b>AGGRESSIVE СИГНАЛ</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Цена: <b>{price:.4f}</b>
RSI: {last['rsi']:.1f}
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    # Сохраняем сигнал в базу
    try:
        session = Session()
        session.add(Signal(symbol=symbol, direction=direction, price=price))
        session.commit()
    except:
        pass

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 OKX Aggressive запущен | Пар: {len(SYMBOLS)}")
    while True:
        for symbol in SYMBOLS[:]:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                signal = get_signal(df, symbol)
                if signal:
                    for uid in list(subscribers):
                        bot.send_message(uid, signal, parse_mode='HTML')
            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
            time.sleep(2)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Подписка на Aggressive сигналы активирована!")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"🟢 Бот работает\nРежим: {MODE.upper()}\nПары: {len(SYMBOLS)}")

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
        bot.reply_to(message, "Формат: /addpair PEPE")

@bot.message_handler(commands=['removepair'])
def removepair(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "⛔ Только админ")
    try:
        pair = message.text.split()[1].upper()
        if pair in SYMBOLS:
            SYMBOLS.remove(pair)
            with open(DATA_FILE, "w") as f:
                json.dump({"symbols": SYMBOLS, "mode": MODE}, f)
            bot.reply_to(message, f"✅ Удалена: {pair}")
        else:
            bot.reply_to(message, "Такой пары нет")
    except:
        bot.reply_to(message, "Формат: /removepair BTC")

@bot.message_handler(commands=['stats'])
def stats(message):
    session = Session()
    total = session.query(Signal).count()
    long = session.query(Signal).filter_by(direction="LONG").count()
    short = session.query(Signal).filter_by(direction="SHORT").count()
    bot.reply_to(message, f"📊 Статистика сигналов:\n\nВсего: {total}\nLONG: {long}\nSHORT: {short}")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот полностью готов!")
    bot.infinity_polling()