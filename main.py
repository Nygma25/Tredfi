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

# ================= НАСТРОЙКИ FUTURES =================
DATA_FILE = "pairs.json"
LEVERAGE = 10
MIN_VOLUME = 1000000  # $1M

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        SYMBOLS = json.load(f)
else:
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump(SYMBOLS, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 900  # 15 минут

# Bybit Futures
exchange = ccxt.bybit({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',   # Futures режим
    }
})

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
    leverage = Column(Integer)

Base.metadata.create_all(engine)

# ================= СИГНАЛЫ =================
def get_signal(df, symbol):
    if len(df) < 60:
        return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    volume = float(last['volume'])
    
    if volume * price < MIN_VOLUME:
        return None

    # Индикаторы
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    direction = None
    strategy = ""

    # Основная стратегия: EMA + RSI + Volume
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 52):
        direction = "LONG"
        strategy = "EMA_CROSS"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 48):
        direction = "SHORT"
        strategy = "EMA_CROSS"

    if not direction:
        return None

    atr = float(last['atr']) if not pd.isna(last['atr']) else price * 0.01
    sl = round(price - atr * 1.8 if direction == "LONG" else price + atr * 1.8, 4)
    tp = round(price + atr * 3.5 if direction == "LONG" else price - atr * 3.5, 4)

    text = f"""
🚨 <b>BYBIT FUTURES СИГНАЛ</b> 🚨

<b>{symbol}</b> — <b>{direction}</b> ×{LEVERAGE}
Стратегия: {strategy}
Цена: <b>{price:.4f}</b>
SL: <b>{sl}</b>
TP: <b>{tp}</b>
RSI: {last['rsi']:.1f}
Объём: ${int(volume*price/1000000)}M
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print("🚀 Bybit Futures мониторинг запущен...")
    while True:
        for symbol in SYMBOLS:
            try:
                # Для Futures используем формат BTC/USDT:USDT если нужно
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                signal_text = get_signal(df, symbol)
                if signal_text:
                    for user_id in list(subscribers):
                        try:
                            bot.send_message(user_id, signal_text, parse_mode='HTML')
                        except:
                            subscribers.discard(user_id)
            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
            time.sleep(3)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Вы подписались на **Bybit Futures** сигналы!\nЛонги и Шорты ×10")

@bot.message_handler(commands=['stop'])
def stop(message):
    subscribers.discard(message.chat.id)
    bot.reply_to(message, "❌ Вы отписались.")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"""🟢 <b>Bybit Futures Bot</b>
Подписчиков: {len(subscribers)}
Пары: {len(SYMBOLS)}
Леверидж: ×{LEVERAGE}
Таймфрейм: {TIMEFRAME}""", parse_mode='HTML')

# Добавь другие команды при необходимости

if __name__ == "__main__":
    if not TOKEN or ADMIN_ID == 0:
        print("❌ Добавь TOKEN и ADMIN_ID в Variables на Railway!")
    else:
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        print("🤖 Bybit Futures бот запущен!")
        bot.infinity_polling()