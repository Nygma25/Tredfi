import telebot
from telebot import types
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import threading
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN)
subscribers = set()
price_alerts = {}  # Для алертов

# ================= 100+ ПАР =================
DATA_FILE = "config.json"
MODE = "aggressive"

default_pairs = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "TON/USDT", "SUI/USDT",
    "WIF/USDT", "PEPE/USDT", "BONK/USDT", "POPCAT/USDT", "SHIB/USDT", "FLOKI/USDT",
    "BRETT/USDT", "MEW/USDT", "PNUT/USDT", "MOODENG/USDT", "GOAT/USDT", "NEIRO/USDT",
    "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "ADA/USDT", "BNB/USDT", "TRX/USDT",
    "ARB/USDT", "OP/USDT", "HBAR/USDT", "KAS/USDT", "TIA/USDT", "SEI/USDT",
    "ONDO/USDT", "NOT/USDT", "PIXEL/USDT", "RUNE/USDT", "FET/USDT", "INJ/USDT",
    "TAO/USDT", "FIL/USDT", "DOT/USDT", "LTC/USDT", "BCH/USDT", "UNI/USDT",
    "AAVE/USDT", "APT/USDT", "MKR/USDT", "PENDLE/USDT", "FTM/USDT", "ALGO/USDT",
    "VET/USDT", "XLM/USDT", "EOS/USDT", "ETC/USDT", "ATOM/USDT", "MATIC/USDT",
    "RENDER/USDT", "GALA/USDT", "IMX/USDT", "THETA/USDT", "SAND/USDT", "MANA/USDT"
]

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        config = json.load(f)
        SYMBOLS = config.get("symbols", default_pairs)
        MODE = config.get("mode", "aggressive")
else:
    SYMBOLS = default_pairs
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 600

exchange = ccxt.okx({'enableRateLimit': True})

# ================= БАЗА ДАННЫХ =================
Base = declarative_base()
engine = create_engine('sqlite:///signals.db', echo=False)
Session = sessionmaker(bind=engine)

class Signal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String)
    direction = Column(String)
    entry_price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    result = Column(String)  # WIN / LOSS

Base.metadata.create_all(engine)

# ================= КНОПКИ ВНИЗУ =================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📊 Статус", "📋 Пары")
    markup.add("➕ Добавить пару", "🗑 Удалить пару")
    markup.add("📈 Статистика", "🔔 Алерт")
    return markup

# ================= СТРАТЕГИЯ =================
def get_signal(df, symbol):
    if len(df) < 60:
        return None
    
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    atr = float(last['atr']) if not pd.isna(last['atr']) else price * 0.015

    direction = None
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 48):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 52):
        direction = "SHORT"

    if not direction:
        return None

    sl = round(price - atr * 1.8 if direction == "LONG" else price + atr * 1.8, 4)
    tp = round(price + atr * 3.5 if direction == "LONG" else price - atr * 3.5, 4)

    text = f"""
🚨 <b>AGGRESSIVE СИГНАЛ</b> 🚨

<b>{symbol}</b> — <b>{direction}</b>
Вход: <b>{price:.4f}</b>
Stop Loss: <b>{sl}</b>
Take Profit: <b>{tp}</b>
RSI: {last['rsi']:.1f}
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    # Сохраняем в базу
    try:
        session = Session()
        session.add(Signal(symbol=symbol, direction=direction, entry_price=price, sl=sl, tp=tp))
        session.commit()
    except:
        pass

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 Финальная версия запущена | Пар: {len(SYMBOLS)}")
    while True:
        for symbol in SYMBOLS:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                signal = get_signal(df, symbol)
                if signal:
                    for uid in list(subscribers):
                        bot.send_message(uid, signal, parse_mode='HTML')
            except:
                pass
            time.sleep(2)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.send_message(message.chat.id, f"✅ **Финальная версия бота готова!**\nВсего пар: {len(SYMBOLS)}", reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_keyboard(message):
    text = message.text
    if text == "📊 Статус":
        bot.reply_to(message, f"🟢 Бот активен\nПар: {len(SYMBOLS)}\nРежим: Aggressive")
    elif text == "📋 Пары":
        bot.reply_to(message, f"📋 Всего пар: {len(SYMBOLS)}\n\n" + "\n".join(SYMBOLS[:30]) + "\n...")
    elif text == "➕ Добавить пару":
        bot.reply_to(message, "Напиши:\n/addpair PEPE")
    elif text == "🗑 Удалить пару":
        bot.reply_to(message, "Напиши:\n/removepair BTC")
    elif text == "📈 Статистика":
        session = Session()
        total = session.query(Signal).count()
        wins = session.query(Signal).filter_by(result="WIN").count()
        winrate = round((wins / total * 100), 2) if total > 0 else 0
        bot.reply_to(message, f"📊 **Статистика**\n\nВсего сигналов: {total}\nWin Rate: {winrate}%", parse_mode='HTML')
    elif text == "🔔 Алерт":
        bot.reply_to(message, "Напиши:\n/alert BTC 68000")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Финальная версия бота запущена!")
    bot.infinity_polling()