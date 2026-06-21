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
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "SUI/USDT", "WIF/USDT", "PEPE/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 600

exchange = ccxt.okx({'enableRateLimit': True})

# ================= КНОПКИ ВНИЗУ =================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📊 Статус", "📋 Пары")
    markup.add("➕ Добавить пару", "🗑 Удалить пару")
    return markup

# ================= СТРАТЕГИЯ =================
def get_signal(df, symbol):
    if len(df) < 60:
        return None
    
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])

    direction = None
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 48):
        direction = "LONG"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 52):
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

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 Бот с кнопками внизу запущен | Пар: {len(SYMBOLS)}")
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
    bot.send_message(message.chat.id, 
                     "✅ **Бот готов!**\n\nВыбери действие:", 
                     reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    text = message.text
    if text == "📊 Статус":
        bot.reply_to(message, f"🟢 Бот активен\nПар: {len(SYMBOLS)}\nРежим: Aggressive")
    elif text == "📋 Пары":
        bot.reply_to(message, "📋 Активные пары:\n\n" + "\n".join(SYMBOLS))
    elif text == "➕ Добавить пару":
        bot.reply_to(message, "Напиши:\n/addpair PEPE")
    elif text == "🗑 Удалить пару":
        bot.reply_to(message, "Напиши:\n/removepair BTC")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот с постоянными кнопками внизу запущен!")
    bot.infinity_polling()