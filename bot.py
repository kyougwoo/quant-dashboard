import os, sys, time, json, requests
import pandas as pd
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(text):
    print("▶️ 텔레그램 전송 시도 중...")
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=5)
    except: pass

def calculate_cloud_indicators(df):
    if df is None or len(df) < 200: return None, None
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean())))
    df['RSI'] = df['RSI'].fillna(50)
    
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['ATR'] = df[['High', 'Low', 'Close']].apply(lambda x: max(x['High']-x['Low'], abs(x['High']-df['Close'].shift(1).loc[x.name]), abs(x['Low']-df['Close'].shift(1).loc[x.name])), axis=1).rolling(14).mean()
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest, prev = df.iloc[-1], df.iloc[-2]
    
    indicators = {
        "EMA15": float(latest['EMA15']),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']),
        "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "5/15일선 정배열": bool(latest['EMA5'] > latest['EMA15'])}
    }
    return float(latest['Close']), indicators

def run_afternoon_screener():
    print("🔍 [오후 타점 스크리너 기동 시작]")
    send_telegram("🔍 <b>[오후 타점 스크리너 기동 중...]</b>\n한국 우량주 정밀 타점을 분석합니다.")
    sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270", "KB금융":"105560", "POSCO홀딩스":"005490", "NAVER":"035420", "알테오젠":"196170"}
    
    res_list = []
    for n, c in sl.items():
        try:
            p, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=500)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                
                if sc >= 1 and ind.get("Is_Above_Monthly_EMA10") and ind['MACD_Cross']:
                    tar_p = p + (ind['ATR'] * 4)
                    stop_p = p - (ind['ATR'] * 2)
                    entry2 = ind['EMA15']
                    rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0
                    
                    res_list.append({
                        "name": n, "price": p, "entry2": entry2, 
                        "target": tar_p, "stop": stop_p, "rr_2": rr_2
                    })
        except: pass
        
    msg = f"🚀 <b>[클라우드 스크리너 마감 보고]</b>\n\n총 {len(res_list)}개 타점 종목 발견!\n\n"
    for r in res_list: 
        # 💡 [업그레이드] 1/2차 타점 및 손익비(매력도) 전송
        msg += f"🔥 <b>{r['name']}</b>\n"
        msg += f" └ 🎯 <b>매수:</b> 1차 {int(r['price']):,}원 / 2차 {int(r['entry2']):,}원\n"
        msg += f" └ 🎯 <b>목표:</b> {int(r['target']):,}원\n"
        msg += f" └ 🛡️ <b>손절:</b> {int(r['stop']):,}원\n"
        msg += f" └ ⚖️ <b>손익비(매력도):</b> 2차 진입시 {r['rr_2']:.1f}배 극대화\n\n"
        
    if not res_list: msg += "월봉 10선 및 RSI/MACD 기준 안전한 매수 타점 종목이 없습니다."
    send_telegram(msg)
    print("✅ 스크리너 완료")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "afternoon"
    if mode == "afternoon": run_afternoon_screener()
    else: print("모닝 브리핑은 생략되었습니다.")
