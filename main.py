import telebot
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import threading
import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# ================= НАСТРОЙКИ =================
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
TIMEFRAME = "15m"
CHECK_INTERVAL = 900  # 15 минут

bot = telebot.TeleBot(TOKEN)
subscribers = set()

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
    sl = Column(Float)
    tp = Column(Float)

Base.metadata.create_all(engine)

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# ================= ИНДИКАТОРЫ =================
def calculate_indicators(df):
    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df

def get_signal(df, symbol):
    if len(df) < 50:
        return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    atr = float(last['atr']) if not pd.isna(last['atr']) else 0

    # EMA Crossover + RSI фильтр
    if (prev['ema9'] < prev['ema21'] and last['ema9'] > last['ema21'] and last['rsi'] > 50):
        direction = "BUY"
        strategy = "EMA_CROSS"
    elif (prev['ema9'] > prev['ema21'] and last['ema9'] < last['ema21'] and last['rsi'] < 50):
        direction = "SELL"
        strategy = "EMA_CROSS"
    else:
        return None

    sl = round(price - atr * 1.5 if direction == "BUY" else price + atr * 1.5, 4)
    tp = round(price + atr * 3.0 if direction == "BUY" else price - atr * 3.0, 4)

    text = f"""
🚨 <b>АВТО СИГНАЛ</b> 🚨

{symbol} — <b>{direction}</b>
Стратегия: {strategy}
Цена: <b>{price:.4f}</b>
SL: <b>{sl}</b>
TP: <b>{tp}</b>
RSI: {last['rsi']:.1f}
Время: {datetime.now().strftime("%H:%M")}
    """.strip()

    # Сохранение в БД
    try:
        session = Session()
        new_sig = Signal(
            symbol=symbol,
            direction=direction,
            price=price,
            strategy=strategy,
            sl=sl,
            tp=tp
        )
        session.add(new_sig)
        session.commit()
    except:
        pass

    return text

# ================= МОНИТОРИНГ =================
def monitor():
    print("🚀 Мониторинг рынка запущен...")
    while True:
        for symbol in SYMBOLS:
            try:
                bars = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df = calculate_indicators(df)
                
                signal_text = get_signal(df, symbol)
                if signal_text:
                    for user_id in list(subscribers):
                        try:
                            bot.send_message(user_id, signal_text, parse_mode='HTML')
                        except Exception:
                            subscribers.discard(user_id)
            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
            time.sleep(3)
        time.sleep(CHECK_INTERVAL)

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start(message):
    subscribers.add(message.chat.id)
    bot.reply_to(message, "✅ Вы подписались на автоматические сигналы!\nБот работает 24/7 на Railway.")

@bot.message_handler(commands=['stop'])
def stop(message):
    subscribers.discard(message.chat.id)
    bot.reply_to(message, "❌ Вы отписались от сигналов.")

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, f"""🟢 <b>Бот активен</b>
Подписчиков: {len(subscribers)}
Пары: {len(SYMBOLS)}
Таймфрейм: {TIMEFRAME}""", parse_mode='HTML')

@bot.message_handler(commands=['history'])
def history(message):
    session = Session()
    signals = session.query(Signal).order_by(Signal.timestamp.desc()).limit(10).all()
    if not signals:
        bot.reply_to(message, "Пока нет сигналов.")
        return
    text = "📜 <b>Последние сигналы:</b>\n\n"
    for s in signals:
        text += f"{s.timestamp.strftime('%d.%m %H:%M')} | {s.symbol} | {s.direction}\n"
    bot.reply_to(message, text, parse_mode='HTML')

# ================= ЗАПУСК =================
if __name__ == "__main__":
    if not TOKEN or ADMIN_ID == 0:
        print("❌ Ошибка: Добавьте TOKEN и ADMIN_ID в Variables на Railway!")
    else:
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        
        print("🤖 Бот успешно запущен на Railway!")
        bot.infinity_polling()