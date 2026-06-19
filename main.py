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
    strategy = "MULTI"

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
🚨 <b>BYBIT FUTURES</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Стратегия: {strategy}
Цена: <b>{price:.4f}</b>
SL: <b>{sl}</b>
TP: <b>{tp}</b>
RSI: {last['rsi']:.1f} | ST: {'Bull' if last.get('supertrend') == 1 else 'Bear'}
Режим: {MODE.upper()}
Время: {datetime.now().strftime("%d.%m %H:%M")}
    """.strip()

    # Сохранение сигнала
    try:
        session = Session()
        session.add(Signal(symbol=symbol, direction=direction, price=price, strategy=strategy, mode=MODE))
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
            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
            time.sleep(3)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Вы подписались на улучшенные Bybit Futures сигналы!")

@bot.message_handler(commands=['stop'])
def stop(message):
    subscribers.discard(message.chat.id)
    bot.reply_to(message, "❌ Отписка выполнена.")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"🟢 Бот активен\nПодписчиков: {len(subscribers)}\nПары: {len(SYMBOLS)}\nРежим: {MODE.upper()}", parse_mode='HTML')

@bot.message_handler(commands=['pairs'])
def pairs(message):
    text = "📋 Текущие пары:\n\n" + "\n".join(SYMBOLS)
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
            save_config()
            bot.reply_to(message, f"✅ Добавлена: {pair}")
        else:
            bot.reply_to(message, "Уже есть")
    except:
        bot.reply_to(message, "Формат: /addpair SOL")

@bot.message_handler(commands=['removepair'])
def removepair(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        pair = message.text.split()[1].upper()
        if pair in SYMBOLS:
            SYMBOLS.remove(pair)
            save_config()
            bot.reply_to(message, f"✅ Удалена: {pair}")
    except:
        bot.reply_to(message, "Формат: /removepair BTC")

def save_config():
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

# ================= ЗАПУСК =================
if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Улучшенный бот запущен!")
    bot.infinity_polling()