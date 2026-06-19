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

SYMBOLS = []
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r") as f:
            config = json.load(f)
            SYMBOLS = config.get("symbols", [])
            MODE = config.get("mode", "conservative")
    except:
        pass

if not SYMBOLS:
    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "TON/USDT", "SUI/USDT", "WIF/USDT"]
    with open(DATA_FILE, "w") as f:
        json.dump({"symbols": SYMBOLS, "mode": MODE}, f)

TIMEFRAME = "15m"
CHECK_INTERVAL = 900

exchange = ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'future'}})

# ================= БАЗА =================
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

# ================= КНОПКИ =================
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Статус", callback_data="status"),
        types.InlineKeyboardButton("📋 Пары", callback_data="pairs"),
        types.InlineKeyboardButton("🔔 Установить алерт", callback_data="alert"),
        types.InlineKeyboardButton("📈 Мои алерты", callback_data="myalerts")
    )
    markup.add(
        types.InlineKeyboardButton("➕ Добавить пару", callback_data="addpair"),
        types.InlineKeyboardButton("🗑 Удалить пару", callback_data="removepair"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats")
    )
    return markup

# ================= ОБРАБОТКА КНОПОК =================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "status":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"🟢 Бот активен\nПары: {len(SYMBOLS)}\nРежим: {MODE.upper()}")
    elif call.data == "pairs":
        bot.answer_callback_query(call.id)
        text = "📋 Активные пары:\n\n" + "\n".join(SYMBOLS)
        bot.send_message(call.message.chat.id, text)
    elif call.data == "alert":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Отправь команду:\n/alert BTC 68000")
    elif call.data == "myalerts":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Покажу твои алерты (/myalerts)")
    # Можно добавить остальные обработчики позже

# ================= МОНИТОРИНГ (упрощён) =================
def monitor():
    print("🚀 Бот с кнопками запущен!")
    while True:
        # Здесь остаётся логика сигналов (как раньше)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.send_message(message.chat.id, 
                     "✅ Добро пожаловать в авто-сигнал бот!\n\nВыбери действие ниже 👇", 
                     reply_markup=main_menu())

@bot.message_handler(commands=['status', 'pairs', 'alert'])
def handle_commands(message):
    # Можно оставить старые команды
    bot.send_message(message.chat.id, "Используй кнопки ниже", reply_markup=main_menu())

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот запущен с меню кнопок!")
    bot.infinity_polling()