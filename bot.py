# ============================================
#     AI TRADING BOT — COMPLETE
#     GSM Hosting Version
#     By: Sindhu Soomro
# ============================================

import ccxt
import pandas as pd
import numpy as np
import pandas_ta as pta
import requests
import json
import time
import random
import groq as groq_lib
from datetime import datetime, timezone, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================
# API KEYS — YAHAN APNI KEYS DALO
# ============================================
OKX_API_KEY        = "a94c2397-7361-47b6-aa2d-3fa8299c7bc7"
OKX_SECRET_KEY     = "6043BE0805DDB5A51F8D066238C21731"
OKX_PASSPHRASE     = "Yasirali123."
TELEGRAM_TOKEN     = "8637348063:AAGR3NtGNKisZMtdAA5t0TeVRiNTVgxhJVk"
TELEGRAM_CHAT_ID   = "6232825288"
GROQ_API_KEY       = "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"

# ============================================
# CONNECTIONS
# ============================================
exchange = ccxt.okx({
    'apiKey':   OKX_API_KEY,
    'secret':   OKX_SECRET_KEY,
    'password': OKX_PASSPHRASE,
})

groq_client = groq_lib.Groq(api_key=GROQ_API_KEY)

# ============================================
# COINS
# ============================================
TIER1 = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT']
TIER2 = ['LINK/USDT','AVAX/USDT','ADA/USDT','DOT/USDT','ARB/USDT',
         'APT/USDT','NEAR/USDT','UNI/USDT','ATOM/USDT','OP/USDT']
TIER3 = ['SUI/USDT','INJ/USDT','DOGE/USDT','LTC/USDT','ALGO/USDT',
         'AAVE/USDT','RUNE/USDT','FIL/USDT','XLM/USDT','TIA/USDT']
ALL_COINS = TIER1 + TIER2 + TIER3

# ============================================
# GLOBALS
# ============================================
daily_pnl      = 0
daily_trades   = 0
bot_active     = True
signals_today  = []
last_update_id = 0

# ============================================
# TELEGRAM
# ============================================
def send_telegram(message):
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ============================================
# DATA FETCH
# ============================================
def fetch_data(symbol, timeframe, limit=200):
    tf_map = {
        '1M':'1M','1W':'1w','1w':'1w',
        '1D':'1d','1d':'1d',
        '4H':'4h','4h':'4h',
        '1H':'1h','1h':'1h',
        '15M':'15m','15m':'15m',
    }
    tf = tf_map.get(timeframe, timeframe)
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        if not ohlcv or len(ohlcv) < 10:
            return None
        df = pd.DataFrame(ohlcv,
            columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        for col in ['open','high','low','close','volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float)
        return df
    except Exception as e:
        print(f"Fetch Error {symbol} {tf}: {e}")
        return None

# ============================================
# INDICATORS
# ============================================
def calculate_indicators(df):
    try:
        if df is None or len(df) < 50:
            return None
        df = df.copy()
        df = df.sort_values('timestamp').reset_index(drop=True)
        for col in ['open','high','low','close','volume']:
            df[col] = df[col].astype(float)

        c = df['close']
        h = df['high']
        l = df['low']
        v = df['volume']

        # EMA
        for length, name in [(9,'ema9'),(20,'ema20'),(50,'ema50'),(100,'ema100'),(200,'ema200')]:
            result = pta.ema(c, length=length)
            df[name] = result.fillna(c) if result is not None else c

        # RSI
        result = pta.rsi(c, length=14)
        df['rsi'] = result.fillna(50) if result is not None else pd.Series([50]*len(df))

        # MACD
        try:
            macd = pta.macd(c, fast=12, slow=26, signal=9)
            if macd is not None:
                df['macd']        = macd.iloc[:,0].fillna(0)
                df['macd_hist']   = macd.iloc[:,1].fillna(0)
                df['macd_signal'] = macd.iloc[:,2].fillna(0)
            else:
                df['macd'] = df['macd_hist'] = df['macd_signal'] = 0.0
        except:
            df['macd'] = df['macd_hist'] = df['macd_signal'] = 0.0

        # ATR
        try:
            result = pta.atr(h, l, c, length=14)
            df['atr'] = result.fillna(c*0.01) if result is not None else c*0.01
        except:
            df['atr'] = c * 0.01

        # Bollinger Bands
        try:
            bb = pta.bbands(c, length=20, std=2)
            if bb is not None:
                df['bb_upper'] = bb.iloc[:,0].fillna(c*1.02)
                df['bb_mid']   = bb.iloc[:,1].fillna(c)
                df['bb_lower'] = bb.iloc[:,2].fillna(c*0.98)
            else:
                df['bb_upper'] = c*1.02
                df['bb_mid']   = c
                df['bb_lower'] = c*0.98
        except:
            df['bb_upper'] = c*1.02
            df['bb_mid']   = c
            df['bb_lower'] = c*0.98

        # Keltner
        try:
            kc = pta.kc(h, l, c, length=20)
            if kc is not None:
                df['kc_upper'] = kc.iloc[:,2].fillna(c*1.02)
                df['kc_lower'] = kc.iloc[:,0].fillna(c*0.98)
            else:
                df['kc_upper'] = c*1.02
                df['kc_lower'] = c*0.98
        except:
            df['kc_upper'] = c*1.02
            df['kc_lower'] = c*0.98

        # Squeeze
        df['squeeze'] = (df['bb_lower'] > df['kc_lower']).astype(int)

        # ADX
        try:
            adx = pta.adx(h, l, c, length=14)
            if adx is not None:
                df['adx']       = adx.iloc[:,0].fillna(20)
                df['dmi_plus']  = adx.iloc[:,1].fillna(0)
                df['dmi_minus'] = adx.iloc[:,2].fillna(0)
            else:
                df['adx'] = 20.0
                df['dmi_plus'] = df['dmi_minus'] = 0.0
        except:
            df['adx'] = 20.0
            df['dmi_plus'] = df['dmi_minus'] = 0.0

        # MFI
        try:
            result = pta.mfi(h, l, c, v, length=14)
            df['mfi'] = result.fillna(50) if result is not None else pd.Series([50]*len(df))
        except:
            df['mfi'] = 50.0

        # VWAP
        df['vwap'] = (c * v).cumsum() / v.cumsum()
        df['vwap'] = df['vwap'].fillna(c)

        # OBV
        try:
            result = pta.obv(c, v)
            df['obv'] = result.fillna(0) if result is not None else pd.Series([0]*len(df))
            df['obv_ma'] = df['obv'].rolling(20).mean().fillna(0)
        except:
            df['obv'] = df['obv_ma'] = 0.0

        # CVD
        df['cvd'] = (v * np.where(c > df['open'], 1, -1)).cumsum()

        # Volume Spike
        df['vol_ma']    = v.rolling(20).mean().fillna(v)
        df['vol_spike'] = (v / df['vol_ma']).fillna(1.0)

        # Pivot
        df['pivot'] = (h + l + c) / 3
        df['r1']    = 2*df['pivot'] - l
        df['s1']    = 2*df['pivot'] - h

        # Trend
        df['trend'] = np.where(df['ema50'] > df['ema200'], 'BULL', 'BEAR')

        return df
    except Exception as e:
        print(f"Indicator Error: {e}")
        return None

# ============================================
# SMC
# ============================================
def find_swing_points(df, lookback=10):
    highs, lows = [], []
    for i in range(lookback, len(df)-lookback):
        if df['high'].iloc[i] == df['high'].iloc[i-lookback:i+lookback].max():
            highs.append((i, float(df['high'].iloc[i])))
        if df['low'].iloc[i] == df['low'].iloc[i-lookback:i+lookback].min():
            lows.append((i, float(df['low'].iloc[i])))
    return highs, lows

def detect_bos(df):
    try:
        highs, lows = find_swing_points(df)
        last = float(df['close'].iloc[-1])
        bos_bull = len(highs)>=2 and last>highs[-1][1]>highs[-2][1]
        bos_bear = len(lows)>=2  and last<lows[-1][1]<lows[-2][1]
        return bos_bull, bos_bear
    except:
        return False, False

def detect_choch(df):
    try:
        highs, lows = find_swing_points(df)
        choch_bull = len(lows)>=2  and lows[-1][1]>lows[-2][1]
        choch_bear = len(highs)>=2 and highs[-1][1]<highs[-2][1]
        return choch_bull, choch_bear
    except:
        return False, False

def find_order_blocks(df, lookback=50):
    try:
        last_close = float(df['close'].iloc[-1])
        bull_ob = bear_ob = None
        for i in range(max(0,len(df)-lookback), len(df)-5):
            c  = float(df['close'].iloc[i])
            o  = float(df['open'].iloc[i])
            c1 = float(df['close'].iloc[i+1])
            o1 = float(df['open'].iloc[i+1])
            h  = float(df['high'].iloc[i])
            l  = float(df['low'].iloc[i])
            if c<o and c1>o1 and c1>h:
                if l<last_close<h*1.02:
                    bull_ob = {'high':h,'low':l,'mid':(h+l)/2}
            if c>o and c1<o1 and c1<l:
                if l*0.98<last_close<h:
                    bear_ob = {'high':h,'low':l,'mid':(h+l)/2}
        return bull_ob, bear_ob
    except:
        return None, None

def find_fvg(df, lookback=50):
    try:
        bull_fvg = bear_fvg = None
        last_close = float(df['close'].iloc[-1])
        for i in range(max(0,len(df)-lookback), len(df)-2):
            h0 = float(df['high'].iloc[i])
            l2 = float(df['low'].iloc[i+2])
            l0 = float(df['low'].iloc[i])
            h2 = float(df['high'].iloc[i+2])
            if l2>h0 and h0<last_close<l2:
                bull_fvg = {'top':l2,'bottom':h0}
            if l0>h2 and h2<last_close<l0:
                bear_fvg = {'top':l0,'bottom':h2}
        return bull_fvg, bear_fvg
    except:
        return None, None

def find_liquidity(df, lookback=50):
    try:
        recent = df.tail(lookback)
        bsl    = float(recent['high'].max())
        ssl    = float(recent['low'].min())
        last_h = float(df['high'].iloc[-1])
        last_l = float(df['low'].iloc[-1])
        last_c = float(df['close'].iloc[-1])
        return {
            'bsl':bsl,'ssl':ssl,
            'liq_grab_bull': last_l<ssl and last_c>ssl,
            'liq_grab_bear': last_h>bsl and last_c<bsl,
        }
    except:
        return {'bsl':0,'ssl':0,'liq_grab_bull':False,'liq_grab_bear':False}

def get_htf_bias(symbol):
    try:
        scores = []
        for tf in ['1d','4h']:
            try:
                df = fetch_data(symbol, tf, 200)
                if df is None or len(df)<50: continue
                df = calculate_indicators(df)
                if df is None: continue
                last   = df.iloc[-1]
                ema50  = float(last.get('ema50',  0) or 0)
                ema200 = float(last.get('ema200', 0) or 0)
                if ema50>0 and ema200>0:
                    scores.append(1 if ema50>ema200 else -1)
            except:
                continue
        if not scores: return 'NEUTRAL'
        avg = sum(scores)/len(scores)
        return 'BULL' if avg>=0.5 else 'BEAR' if avg<=-0.5 else 'NEUTRAL'
    except:
        return 'NEUTRAL'

def get_funding_rate(symbol):
    try:
        ticker = exchange.fetch_funding_rate(symbol+':USDT')
        return float(ticker['fundingRate'])
    except:
        return 0.0

def smc_analysis(symbol):
    try:
        df_15m = fetch_data(symbol,'15m',200)
        df_4h  = fetch_data(symbol,'4h', 200)
        if df_15m is None or df_4h is None: return None
        df_15m = calculate_indicators(df_15m)
        df_4h  = calculate_indicators(df_4h)
        if df_15m is None or df_4h is None: return None
        return {
            'symbol':     symbol,
            'htf_bias':   get_htf_bias(symbol),
            'bos_bull':   detect_bos(df_4h)[0],
            'bos_bear':   detect_bos(df_4h)[1],
            'choch_bull': detect_choch(df_4h)[0],
            'choch_bear': detect_choch(df_4h)[1],
            'bull_ob':    find_order_blocks(df_15m)[0],
            'bear_ob':    find_order_blocks(df_15m)[1],
            'bull_fvg':   find_fvg(df_15m)[0],
            'bear_fvg':   find_fvg(df_15m)[1],
            'liquidity':  find_liquidity(df_4h),
            'df_15m':     df_15m,
        }
    except Exception as e:
        print(f"SMC Error {symbol}: {e}")
        return None

# ============================================
# MACRO
# ============================================
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        d = r.json()['data'][0]
        return int(d['value']), d['value_classification']
    except:
        return 50, "Neutral"

def get_btc_dominance():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        return round(r.json()['data']['market_cap_percentage']['btc'],2)
    except:
        return 50.0

def get_session_pkt():
    pkt  = timezone(timedelta(hours=5))
    hour = datetime.now(pkt).hour
    if 13<=hour<17:   return "London", 2
    elif 18<=hour<20: return "London/NY Overlap", 4
    elif 20<=hour<22: return "NY Session", 3
    else:             return "Asian/Off", 0

def get_market_regime(symbol):
    try:
        df   = fetch_data(symbol,'1d',100)
        df   = calculate_indicators(df)
        last = df.iloc[-1]
        if float(last['ema20'])>float(last['ema50'])>float(last['ema200']): return 'BULL'
        elif float(last['ema20'])<float(last['ema50'])<float(last['ema200']): return 'BEAR'
        else: return 'SIDEWAYS'
    except:
        return 'NEUTRAL'

# ============================================
# AI
# ============================================
def build_prompt(symbol, smc, df, macro):
    last = df.iloc[-1]
    return f"""You are a professional crypto futures trader.
Analyze and respond in JSON ONLY. No extra text.
COIN:{symbol} PRICE:{float(last['close']):.2f}
TREND:{last['trend']} EMA50:{float(last['ema50']):.2f}
EMA200:{float(last['ema200']):.2f} RSI:{float(last['rsi']):.1f}
MACD:{float(last['macd']):.4f} ADX:{float(last['adx']):.1f}
MFI:{float(last['mfi']):.1f} VOL:{float(last['vol_spike']):.2f}x
HTF:{smc['htf_bias']} BOS_BULL:{smc['bos_bull']}
BOS_BEAR:{smc['bos_bear']} CHOCH_BULL:{smc['choch_bull']}
BULL_OB:{smc['bull_ob'] is not None} BULL_FVG:{smc['bull_fvg'] is not None}
LIQ_GRAB:{smc['liquidity']['liq_grab_bull']}
FG:{macro['fg_value']} BTC_DOM:{macro['btc_dom']}%
SESSION:{macro['session']} REGIME:{macro['regime']}
FUNDING:{macro['funding']:.4%}
Reply ONLY this JSON:
{{"direction":"LONG" or "SHORT" or "NO_TRADE","score":0-100,"confidence":"HIGH" or "MEDIUM" or "LOW","reasons":["r1","r2","r3"],"summary":"one line"}}"""

def parse_json(text):
    try:
        text  = text.strip()
        start = text.find('{')
        end   = text.rfind('}')+1
        if start!=-1 and end>start:
            return json.loads(text[start:end])
    except:
        return None

def ask_groq(prompt, model):
    try:
        r = groq_client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content":prompt}],
            temperature=0.1,
            max_tokens=300
        )
        return parse_json(r.choices[0].message.content)
    except Exception as e:
        print(f"Groq Error {model}: {e}")
        return None

def get_ai_vote(prompt):
    r1 = ask_groq(prompt, "llama-3.3-70b-versatile")
    time.sleep(1)
    r2 = ask_groq(prompt, "llama-3.3-70b-versatile")
    time.sleep(1)
    r3 = ask_groq(prompt, "llama-3.1-8b-instant")

    results = [r for r in [r1,r2,r3] if r and 'direction' in r and 'score' in r]
    if not results: return 'NO_TRADE', 0, 0

    directions = [r['direction'] for r in results]
    long_v  = directions.count('LONG')
    short_v = directions.count('SHORT')

    if long_v>=2:    winner,votes = 'LONG',long_v
    elif short_v>=2: winner,votes = 'SHORT',short_v
    else:            winner,votes = 'NO_TRADE',0

    avg = sum(r['score'] for r in results)/len(results)
    return winner, votes, avg

# ============================================
# SCORING
# ============================================
def calculate_score(smc, df, macro, votes):
    score   = 0
    reasons = []
    last    = df.iloc[-1]

    if smc['htf_bias'] in ['BULL','BEAR']:
        score+=15; reasons.append(f"✅ HTF {smc['htf_bias']}")
    else: score+=5

    if smc['bos_bull'] or smc['bos_bear']:
        score+=8; reasons.append("✅ BOS")
    if smc['choch_bull'] or smc['choch_bear']:
        score+=7; reasons.append("✅ CHOCH")

    if smc['bull_ob'] or smc['bear_ob']:
        score+=5; reasons.append("✅ Order Block")
    if smc['bull_fvg'] or smc['bear_fvg']:
        score+=5; reasons.append("✅ FVG")

    if smc['liquidity']['liq_grab_bull'] or smc['liquidity']['liq_grab_bear']:
        score+=10; reasons.append("✅ Liq Grab!")
    else: score+=3

    try:
        rsi = float(last['rsi'])
        score += 2 if rsi<35 or rsi>65 else 1
        if float(last['macd'])>float(last['macd_signal']):
            score+=2; reasons.append("✅ MACD Bull")
        else: score+=1
        if float(last['adx'])>25:
            score+=2; reasons.append("✅ ADX Strong")
        if float(last['mfi'])>50: score+=2
    except: score+=4

    try:
        vs = float(last['vol_spike'])
        if vs>=3.0:   score+=8; reasons.append("✅ Vol 3x!")
        elif vs>=2.0: score+=5; reasons.append("⚠️ Vol 2x")
        else: score+=1
    except: score+=3

    try:
        body  = abs(float(last['close'])-float(last['open']))
        rng   = float(last['high'])-float(last['low'])
        ratio = body/rng if rng>0 else 0
        if ratio>0.7:   score+=8; reasons.append("✅ Strong Candle")
        elif ratio>0.5: score+=5
        else: score+=2
    except: score+=4

    score+=5

    try:
        fg = macro['fg_value']
        score += 3 if fg<25 or fg>75 else 1
        score += 2 if macro['btc_dom']<55 else 1
    except: score+=2

    try:
        f = macro['funding']
        if -0.001<f<0.001:  score+=5; reasons.append("✅ Funding OK")
        elif f<-0.001:      score+=4; reasons.append("✅ Neg Funding")
        else: score+=2
    except: score+=3

    try:
        score+=macro['session_score']
        if macro['session_score']==4: reasons.append("✅ Kill Zone!")
    except: score+=2

    if votes==3:   score+=10; reasons.append("✅ 3/3 AI!")
    elif votes==2: score+=7;  reasons.append("✅ 2/3 AI")
    else:          score-=5

    return min(int(score),100), reasons

# ============================================
# TP/SL — STRUCTURE BASED
# ============================================
def calculate_tp_sl(direction, entry, atr, df):
    try:
        recent = df.tail(100)

        if direction == 'LONG':
            swing_low = float(recent['low'].nsmallest(3).mean())
            sl1       = round(swing_low - atr*0.3, 4)
            sl2       = round(swing_low - atr*0.8, 4)
            sl_dist   = abs(entry - sl1)
            if sl_dist < atr*1.5:
                sl1 = round(entry - atr*1.5, 4)
                sl2 = round(entry - atr*2.0, 4)
                sl_dist = atr*1.5
            tp1 = round(entry + sl_dist*2, 4)
            tp2 = round(entry + sl_dist*3, 4)
            tp3 = round(entry + sl_dist*5, 4)
            tp4 = round(entry + sl_dist*8, 4)
        else:
            swing_high = float(recent['high'].nlargest(3).mean())
            sl1        = round(swing_high + atr*0.3, 4)
            sl2        = round(swing_high + atr*0.8, 4)
            sl_dist    = abs(sl1 - entry)
            if sl_dist < atr*1.5:
                sl1 = round(entry + atr*1.5, 4)
                sl2 = round(entry + atr*2.0, 4)
                sl_dist = atr*1.5
            tp1 = round(entry - sl_dist*2, 4)
            tp2 = round(entry - sl_dist*3, 4)
            tp3 = round(entry - sl_dist*5, 4)
            tp4 = round(entry - sl_dist*8, 4)

        return {
            'entry':round(entry,4),
            'sl1':sl1,'sl2':sl2,
            'tp1':tp1,'tp2':tp2,
            'tp3':tp3,'tp4':tp4,
        }
    except:
        sl = atr * 3.0
        if direction == 'LONG':
            return {
                'entry':round(entry,4),
                'sl1':round(entry-sl,4),'sl2':round(entry-sl*1.5,4),
                'tp1':round(entry+sl*2,4),'tp2':round(entry+sl*3,4),
                'tp3':round(entry+sl*5,4),'tp4':round(entry+sl*8,4),
            }
        else:
            return {
                'entry':round(entry,4),
                'sl1':round(entry+sl,4),'sl2':round(entry+sl*1.5,4),
                'tp1':round(entry-sl*2,4),'tp2':round(entry-sl*3,4),
                'tp3':round(entry-sl*5,4),'tp4':round(entry-sl*8,4),
            }

# ============================================
# FULL ANALYSIS
# ============================================
def full_analysis(symbol):
    print(f"Analyzing: {symbol}")
    try:
        smc = smc_analysis(symbol)
        if not smc: return None

        df_15m = smc['df_15m']
        last   = df_15m.iloc[-1]

        fg_value,fg_label  = get_fear_greed()
        btc_dom            = get_btc_dominance()
        session,sess_score = get_session_pkt()
        regime             = get_market_regime(symbol)
        funding            = get_funding_rate(symbol)

        macro = {
            'fg_value':fg_value,'fg_label':fg_label,
            'btc_dom':btc_dom,'session':session,
            'session_score':sess_score,
            'regime':regime,'funding':funding,
        }

        if regime == 'SIDEWAYS':
            print(f"{symbol} SIDEWAYS — Skip")
            return None

        prompt = build_prompt(symbol,smc,df_15m,macro)
        direction,votes,ai_score = get_ai_vote(prompt)

        if votes < 2:
            print(f"{symbol} AI Vote: {votes}/3 — Skip")
            return None

        score,reasons = calculate_score(smc,df_15m,macro,votes)
        print(f"{symbol} Score: {score}/100 Vote: {votes}/3 → {direction}")

        if score < 75:
            print(f"{symbol} Score low: {score} — Skip")
            return None

        levels = calculate_tp_sl(
            direction,float(last['close']),float(last['atr']),df_15m
        )

        strength = "⭐⭐⭐ STRONG" if score>=85 else "⭐⭐ NORMAL"
        print(f"SIGNAL! {symbol} {direction} {score}/100")

        return {
            'symbol':symbol,'direction':direction,
            'score':score,'votes':votes,
            'levels':levels,'reasons':reasons,
            'macro':macro,'last':last,'strength':strength,
        }
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

# ============================================
# SIGNAL FORMAT
# ============================================
def format_signal(result):
    l    = result['levels']
    m    = result['macro']
    last = result['last']
    reasons = "\n".join(result['reasons'][:5])
    session,_ = get_session_pkt()
    pkt = timezone(timedelta(hours=5))
    t   = datetime.now(pkt).strftime("%d %b %Y %I:%M %p PKT")
    dir_emoji = "🟢 LONG 📈" if result['direction']=='LONG' else "🔴 SHORT 📉"
    strength  = result.get('strength','⭐⭐ NORMAL')

    return f"""
🚀 <b>AI TRADING SIGNAL</b> 🚀
━━━━━━━━━━━━━━━━━━━━
📌 <b>Coin:</b> {result['symbol']}
📊 <b>Direction:</b> {dir_emoji}
🕐 <b>Time:</b> {t}
🌍 <b>Session:</b> {session}
━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY LEVELS</b>
━━━━━━━━━━━━━━━━━━━━
🎯 Entry:     <code>{l['entry']}</code>
🛑 SL1:       <code>{l['sl1']}</code>
🛑 SL2:       <code>{l['sl2']}</code>
✅ TP1 (25%): <code>{l['tp1']}</code> R:R 1:2
✅ TP2 (25%): <code>{l['tp2']}</code> R:R 1:3
✅ TP3 (30%): <code>{l['tp3']}</code> R:R 1:5
🏆 TP4 (20%): <code>{l['tp4']}</code> R:R 1:8
━━━━━━━━━━━━━━━━━━━━
🤖 <b>AI ANALYSIS</b>
━━━━━━━━━━━━━━━━━━━━
📊 Score:   <b>{result['score']}/100</b> {strength}
🗳️ AI Vote: <b>{result['votes']}/3</b> ✅
📈 RSI:     {float(last['rsi']):.1f}
📦 Volume:  {float(last['vol_spike']):.1f}x
💸 Funding: {m['funding']:.4%}
😱 F&G:     {m['fg_value']} ({m['fg_label']})
🏦 BTC Dom: {m['btc_dom']}%
━━━━━━━━━━━━━━━━━━━━
📋 <b>REASONS</b>
━━━━━━━━━━━━━━━━━━━━
{reasons}
━━━━━━━━━━━━━━━━━━━━
⚠️ Risk 1% | 3x MAX | Follow plan!
🤖 AI Trading Bot | Pakistan #1"""

# ============================================
# CHATBOT
# ============================================
def handle_chatbot(text, chat_id):
    global bot_active
    text = text.lower().strip()

    if text=='/start':
        return "🤖 AI Trading Bot!\n/status\n/stats\n/stop\nBTC — Analysis\nETH — Analysis"
    elif text=='/status':
        return f"🤖 {'✅ Active' if bot_active else '❌ Band'}\n📊 Trades: {daily_trades}\n💰 P&L: {daily_pnl}%"
    elif text=='/stats':
        session,_ = get_session_pkt()
        fg,fgl    = get_fear_greed()
        return f"📊 Trades: {daily_trades}\nP&L: {daily_pnl}%\nSession: {session}\nF&G: {fg} ({fgl})"
    elif text=='/stop':
        bot_active=False; return "⛔ Bot band!"
    elif text=='/start_bot':
        bot_active=True; return "✅ Bot chalu!"

    coins_map = {
        'btc':'BTC/USDT','eth':'ETH/USDT','sol':'SOL/USDT',
        'bnb':'BNB/USDT','xrp':'XRP/USDT','ada':'ADA/USDT',
        'doge':'DOGE/USDT','avax':'AVAX/USDT','link':'LINK/USDT',
        'dot':'DOT/USDT','arb':'ARB/USDT','apt':'APT/USDT',
    }

    for coin,symbol in coins_map.items():
        if coin in text:
            send_telegram(f"🔍 {symbol} analyzing...\n⏳ 1-2 min")
            result = full_analysis(symbol)
            if result: return format_signal(result)
            else:
                try:
                    df   = fetch_data(symbol,'1h',5)
                    last = df.iloc[-1]
                    fg,fgl = get_fear_greed()
                    return f"📊 {symbol}\n💰 ${float(last['close']):,.2f}\n😱 F&G: {fg} ({fgl})\n⚠️ No signal"
                except:
                    return f"⚠️ {symbol} — No signal"

    if any(w in text for w in ['market','kaisa','overview']):
        fg,fgl    = get_fear_greed()
        dom       = get_btc_dominance()
        session,_ = get_session_pkt()
        return f"🌍 MARKET\n😱 F&G: {fg} ({fgl})\n🏦 BTC Dom: {dom}%\n🕐 {session}"

    try:
        r = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":"You are a helpful crypto trading assistant. Answer in Urdu/English mix. Be concise."},
                {"role":"user","content":text}
            ],
            max_tokens=200, temperature=0.7
        )
        return r.choices[0].message.content
    except:
        return "🤖 BTC/ETH likh ke analysis lo!"

def process_chatbot():
    global last_update_id
    try:
        url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset":last_update_id+1,"timeout":5}
        r      = requests.get(url,params=params,timeout=10)
        data   = r.json()
        if not data.get('ok'): return
        for update in data.get('result',[]):
            last_update_id = update['update_id']
            try:
                msg     = update.get('message',{})
                text    = msg.get('text','')
                chat_id = msg.get('chat',{}).get('id')
                if text and chat_id:
                    print(f"MSG: {text}")
                    response = handle_chatbot(text,chat_id)
                    if response:
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                            data={"chat_id":chat_id,"text":response,"parse_mode":"HTML"},
                            timeout=10
                        )
            except Exception as e:
                print(f"Update Error: {e}")
    except Exception as e:
        print(f"Chatbot Error: {e}")

# ============================================
# SCANNER
# ============================================
def run_scanner():
    global daily_trades, signals_today
    if not bot_active:
        print("Bot band"); return

    session,sess_score = get_session_pkt()
    if sess_score == 0:
        print(f"{session} — Skip"); return

    print(f"SCAN — {session}")
    for symbol in ALL_COINS:
        try:
            if symbol in signals_today: continue
            result = full_analysis(symbol)
            if result:
                signals_today.append(symbol)
                daily_trades += 1
                send_telegram(format_signal(result))
                print(f"Signal: {symbol}")
            time.sleep(2)
        except Exception as e:
            print(f"Error {symbol}: {e}")
    print(f"Scan done! Trades: {daily_trades}")

# ============================================
# 1 YEAR BACKTEST
# ============================================
def run_backtest():
    print("="*40)
    print("BACKTEST 1 YEAR STARTING")
    print("="*40)

    BACKTEST_COINS  = TIER1 + TIER2[:5]
    INITIAL_BALANCE = 1000
    RISK            = 0.01
    MIN_SCORE       = 60

    def bt_score(df):
        try:
            score = 0
            last  = df.iloc[-1]
            ema50  = float(last.get('ema50',  0) or 0)
            ema200 = float(last.get('ema200', 0) or 0)
            if ema50>ema200: score+=15
            else:            score+=5
            rsi = float(last.get('rsi', 50) or 50)
            score += 8 if rsi<35 or rsi>65 else 4
            adx = float(last.get('adx', 20) or 20)
            score += 8 if adx>25 else 4
            macd     = float(last.get('macd',        0) or 0)
            macd_sig = float(last.get('macd_signal', 0) or 0)
            score += 7 if macd>macd_sig else 3
            vs = float(last.get('vol_spike', 1) or 1)
            if vs>=2.0:   score+=8
            elif vs>=1.5: score+=5
            else:         score+=2
            score += 5+3+3+4
            score += 7 if random.random()<0.70 else -3
            return min(int(score),100)
        except:
            return 0

    def sim_trade(direction, entry, atr, df_f):
        sl  = atr*2.5
        tp1 = entry+(sl*2) if direction=='LONG' else entry-(sl*2)
        tp2 = entry+(sl*3) if direction=='LONG' else entry-(sl*3)
        sl1 = entry-sl     if direction=='LONG' else entry+sl
        for i in range(min(48,len(df_f))):
            h = float(df_f['high'].iloc[i])
            l = float(df_f['low'].iloc[i])
            if direction=='LONG':
                if l<=sl1:   return 'LOSS',-1.0
                elif h>=tp2: return 'WIN',+3.0
                elif h>=tp1: return 'WIN',+1.5
            else:
                if h>=sl1:   return 'LOSS',-1.0
                elif l<=tp2: return 'WIN',+3.0
                elif l<=tp1: return 'WIN',+1.5
        return 'EXPIRED',0

    all_trades  = []
    balance     = INITIAL_BALANCE
    monthly_pnl = {}

    for symbol in BACKTEST_COINS:
        print(f"Testing: {symbol}")
        try:
            df = fetch_data(symbol,'4h',2200)
            if df is None or len(df)<200: continue
            df = calculate_indicators(df)
            if df is None: continue

            coin_trades = coin_wins = 0
            for i in range(200, len(df)-50, 6):
                try:
                    df_s = df.iloc[:i].copy()
                    df_f = df.iloc[i:i+50].copy()
                    if len(df_s)<100: continue
                    last   = df_s.iloc[-1]
                    ema50  = float(last.get('ema50',  0) or 0)
                    ema200 = float(last.get('ema200', 0) or 0)
                    if ema50>ema200:   direction='LONG'
                    elif ema50<ema200: direction='SHORT'
                    else: continue
                    score = bt_score(df_s)
                    if score<MIN_SCORE: continue
                    entry = float(last['close'])
                    atr   = float(last.get('atr',entry*0.01) or entry*0.01)
                    if atr<=0: continue
                    result,pnl_pct = sim_trade(direction,entry,atr,df_f)
                    if result=='EXPIRED': continue
                    trade_pnl  = balance*RISK*pnl_pct
                    balance   += trade_pnl
                    coin_trades+=1
                    if result=='WIN': coin_wins+=1
                    month_key = df_s['timestamp'].iloc[-1].strftime('%Y-%m')
                    if month_key not in monthly_pnl:
                        monthly_pnl[month_key]={'trades':0,'wins':0,'pnl':0}
                    monthly_pnl[month_key]['trades']+=1
                    monthly_pnl[month_key]['wins']+=1 if result=='WIN' else 0
                    monthly_pnl[month_key]['pnl']+=trade_pnl
                    all_trades.append({'symbol':symbol,'result':result,'pnl':trade_pnl})
                except: continue
            wr = coin_wins/coin_trades*100 if coin_trades>0 else 0
            print(f"{symbol}: {coin_trades} trades | {wr:.1f}% WR")
            time.sleep(0.5)
        except Exception as e:
            print(f"Error {symbol}: {e}")

    if all_trades:
        total  = len(all_trades)
        wins   = sum(1 for t in all_trades if t['result']=='WIN')
        losses = sum(1 for t in all_trades if t['result']=='LOSS')
        wr     = wins/total*100
        pnl    = balance-INITIAL_BALANCE
        roi    = pnl/INITIAL_BALANCE*100

        print(f"\nFINAL RESULTS")
        print(f"Start:    ${INITIAL_BALANCE:,.2f}")
        print(f"Final:    ${balance:,.2f}")
        print(f"P&L:      ${pnl:+,.2f}")
        print(f"ROI:      {roi:.1f}%")
        print(f"Win Rate: {wr:.1f}%")
        print(f"Trades:   {total}")

        monthly_breakdown = ""
        for month,data in sorted(monthly_pnl.items()):
            t   = data['trades']
            w   = data['wins']
            p   = data['pnl']
            wr2 = w/t*100 if t>0 else 0
            emoji = "✅" if p>0 else "❌"
            monthly_breakdown += f"\n{month}: {emoji} ${p:+.1f} | {w}/{t} ({wr2:.0f}%)"

        send_telegram(f"""📊 <b>1 YEAR BACKTEST RESULTS</b>

💰 Start:    ${INITIAL_BALANCE:,.2f}
💰 Final:    ${balance:,.2f}
📈 P&L:      ${pnl:+,.2f}
📊 ROI:      {roi:.1f}%
🎯 Win Rate: {wr:.1f}%
✅ Wins:     {wins}
❌ Losses:   {losses}
📊 Trades:   {total}

📅 MONTHLY:
{monthly_breakdown}

🤖 AI Trading Bot""")
        print("Backtest results Telegram pe bheje!")
    else:
        print("Koi trade nahi mila")

# ============================================
# MAIN
# ============================================
def main():
    global bot_active, daily_pnl, daily_trades, signals_today

    print("BOT STARTING...")

    # Run backtest first
    print("Running 1 Year Backtest...")
    run_backtest()
    print("Backtest Complete!")

    # Start bot
    send_telegram("""🤖 <b>AI Trading Bot Chalu!</b>
✅ Active | 📊 25 Coins
⏱️ Scan: 30 min | 🎯 Score: 75+

Commands:
/status — Status
/stats — Today stats
BTC — BTC analysis
Koi bhi sawaal puchein!""")

    scan_count = 0
    while True:
        try:
            process_chatbot()
            scan_count += 1

            # 30 min = 180 × 10sec
            if scan_count >= 180:
                scan_count = 0
                run_scanner()

            pkt = timezone(timedelta(hours=5))
            now = datetime.now(pkt)
            if now.hour==0 and now.minute==0:
                daily_pnl     = 0
                daily_trades  = 0
                bot_active    = True
                signals_today = []
                send_telegram("🔄 Daily Reset!")

            time.sleep(10)

        except KeyboardInterrupt:
            print("Bot band!")
            send_telegram("⛔ Bot band!")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
