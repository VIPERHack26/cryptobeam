from flask import Flask
import ccxt
import pandas as pd
import numpy as np
import requests
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from datetime import datetime

app = Flask(__name__)

# === TELEGRAM CONFIG ===
TELEGRAM_TOKEN = 'your_bot_token'
TELEGRAM_CHAT_ID = 'your_chat_id'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

# === CONFIG ===
EXCHANGE = ccxt.binance()
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'TON/USDT', 'ADA/USDT']
LIMIT = 100

def fetch_data(symbol, timeframe):
    try:
        ohlcv = EXCHANGE.fetch_ohlcv(symbol, timeframe=timeframe, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        return df
    except:
        return None

def apply_indicators(df):
    df['EMA20'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['EMA200'] = EMAIndicator(df['close'], window=200, fillna=True).ema_indicator()
    df['RSI'] = RSIIndicator(df['close'], window=14).rsi()
    macd = MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['ATR'] = atr.average_true_range()
    return df

def evaluate_signal(df_15m, df_1h, symbol):
    latest = df_15m.iloc[-1]
    trend_ok = latest['close'] > latest['EMA200']

    if not trend_ok:
        return None

    volume_avg = df_15m['volume'].rolling(5).mean().iloc[-1]
    volume_spike = latest['volume'] > volume_avg
    price = latest['close']
    atr = latest['ATR']

    score = 0
    if latest['close'] > latest['EMA20'] and latest['MACD'] > latest['MACD_signal']:
        score += 30
    if 50 < latest['RSI'] < 70:
        score += 15
    if volume_spike:
        score += 15
    if df_1h.iloc[-1]['close'] > df_1h.iloc[-1]['EMA20']:
        score += 20

    if score >= 70:
        signal_type = 'BUY'
        tp = price + atr * 1.5
        sl = price - atr
    elif score <= 30:
        signal_type = 'SELL'
        tp = price - atr * 1.5
        sl = price + atr
    else:
        return None

    return {
        'symbol': symbol,
        'type': signal_type,
        'price': price,
        'tp': tp,
        'sl': sl,
        'time': datetime.utcnow().strftime('%H:%M:%S')
    }

def run_bot():
    messages = []
    for symbol in SYMBOLS:
        df_15m = fetch_data(symbol, '15m')
        df_1h = fetch_data(symbol, '1h')
        if df_15m is None or df_1h is None:
            continue
        df_15m = apply_indicators(df_15m)
        df_1h = apply_indicators(df_1h)
        signal = evaluate_signal(df_15m, df_1h, symbol)
        if signal:
            msg = (
                f"{signal['symbol']} ({signal['type']})\n"
                f"Price: {signal['price']:.2f}\n"
                f"TP: {signal['tp']:.2f} | SL: {signal['sl']:.2f}\n"
                f"Time: {signal['time']}"
            )
            messages.append(msg)
            send_telegram_message(msg)
    return messages

@app.route("/")
def home():
    return "Bot is running."

@app.route("/run")
def trigger_bot():
    results = run_bot()
    if results:
        return "<br>".join(results)
    return "No new signals."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
