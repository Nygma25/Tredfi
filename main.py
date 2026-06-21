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

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN)
subscribers = set()

# ================= БОЛЬШОЙ СПИСОК ИЗ 100+ ПАР =================
DATA_FILE = "config.json"
MODE = "aggressive"

default_pairs = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "TON/USDT", "SUI/USDT", "WIF/USDT", "PEPE/USDT", "BONK/USDT",
    "POPCAT/USDT", "SHIB/USDT", "FLOKI/USDT", "BRETT/USDT", "MEW/USDT",
    "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "ADA/USDT", "BNB/USDT",
    "TRX/USDT", "ARB/USDT", "OP/USDT", "HBAR/USDT", "KAS/USDT",
    "TIA/USDT", "SEI/USDT", "ONDO/USDT", "NOT/USDT", "PIXEL/USDT",
    "RUNE/USDT", "FET/USDT", "INJ/USDT", "TAO/USDT", "FIL/USDT",
    "DOT/USDT", "LTC/USDT", "BCH/USDT", "UNI/USDT", "AAVE/USDT",
    "APT/USDT", "MKR/USDT", "PENDLE/USDT", "FTM/USDT", "ALGO/USDT",
    "VET/USDT", "XLM/USDT", "EOS/USDT", "ETC/USDT", "ATOM/USDT",
    "MATIC/USDT", "POL/USDT", "RENDER/USDT", "GALA/USDT", "IMX/USDT",
    "THETA/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT", "SNX/USDT",
    "CRV/USDT", "COMP/USDT", "ZRO/USDT", "ENA/USDT", "WLD/USDT",
    "ORDI/USDT", "STX/USDT", "AR/USDT", "BEAM/USDT", "CFX/USDT",
    "IO/USDT", "TURBO/USDT", "CATI/USDT", "GRASS/USDT", "MOODENG/USDT",
    "HMSTR/USDT", "PNUT/USDT", "GOAT/USDT", "AIXBT/USDT", "NEIRO/USDT",
    "ACT/USDT", "BOME/USDT", "1000SATS/USDT", "1000BONK/USDT", "1000PEPE/USDT"
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

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print(f"🚀 Бот запущен | Пар: {len(SYMBOLS)}")
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
    bot.reply_to(message, f"✅ Подписка активна!\nВсего пар: {len(SYMBOLS)}")

@bot.message_handler(commands=['pairs'])
def pairs(message):
    text = f"📋 Всего пар: {len(SYMBOLS)}\n\n" + "\n".join(SYMBOLS[:50]) + "\n... и другие"
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
            bot.reply_to(message, f"✅ Добавлена: {pair}\nВсего: {len(SYMBOLS)}")
    except:
        bot.reply_to(message, "Формат: /addpair PEPE")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"🟢 Бот активен\nПар: {len(SYMBOLS)}\nРежим: Aggressive")

if __name__ == "__main__":
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print("🤖 Бот с 100+ парами запущен!")
    bot.infinity_polling()