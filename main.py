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
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "TON/USDT", "SUI/USDT", "WIF/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 600

# ←←← ИЗМЕНИЛИ НА BINANCE ←←←
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ... (остальной код остается таким же)

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
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 AGGRESSIVE Binance запущен | Пар: {len(SYMBOLS)}")
    while True:
        for symbol in SYMBOLS:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                signal = get_signal(df, symbol)
                if signal:
                    for uid in list(subscribers):
                        bot.send_message(uid, signal, parse_mode='HTML')
            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
            time.sleep(3)
        time.sleep(CHECK_INTERVAL)

@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Aggressive режим на **Binance** запущен!")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот запущен!")
    bot.infinity_polling()