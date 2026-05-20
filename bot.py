import os, sys, time, json, requests, re
import pandas as pd
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.cloud import firestore
from google.oauth2 import service_account
import textwrap

# --- 1. 환경 변수 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIREBASE_JSON = os.environ.get("FIREBASE_JSON")
USER_ID = os.environ.get("USER_ID", "vip")

def send_telegram(text):
    print("▶️ 텔레그램 전송 시도 중...")
    base_url = "https://" + "api.telegram.org/bot"
    url = f"{base_url}{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
        if res.status_code == 200: print("✅ 텔레그램 메시지 발송 완료!")
    except Exception as e: print(f"🚨 네트워크 오류: {e}")

def get_recent_news(keyword):
    try:
        url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:3] if item.title]
    except: return []

def load_krx_data():
    try: return pd.concat([fdr.StockListing('KOSPI'), fdr.StockListing('KOSDAQ')], ignore_index=True)
    except: return fdr.StockListing('KRX')

def get_screener_target_stocks(db=None):
    sl = {}
    if db:
        try:
            doc = db.collection('users').document(USER_ID).get()
            if doc.exists:
                watchlist = doc.to_dict().get('watchlist', [])
                krx = load_krx_data()
                for w in watchlist:
                    try: sl[w] = krx[krx['Name']==w]['Code'].values[0]
                    except: pass
        except: pass
    sl.update({"삼성전자":"005930", "SK하이닉스":"000660", "알테오젠":"196170", "에코프로비엠":"247540", "영풍":"000670"})
    return sl

def calculate_cloud_indicators(df):
    if df is None or df.empty or len(df) < 200: return None, {}
    df = df.dropna(subset=['Close'])
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    try: current_monthly_ema10 = float(df['Close'].resample('ME').last().ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    indicators = {
        "EMA15": float(latest['EMA15']), "EMA5": float(latest['EMA5']),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
        "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200'])}
    }
    return df, indicators

def get_ai_analysis(prompt, is_json=True):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    config = {"response_mime_type": "application/json"} if is_json else {}
    res = model.generate_content(prompt, generation_config=config)
    if is_json: return json.loads(res.text.replace("```json", "").replace("```", "").strip())
    return res.text.strip()

def get_db_client():
    if not FIREBASE_JSON: return None
    try:
        creds_dict = json.loads(FIREBASE_JSON, strict=False)
        if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return firestore.Client(credentials=creds, project=creds_dict.get("project_id"))
    except: return None

# --- 1. 아침 모닝 브리핑 (트레일링 스탑 & 뉴스 감성 분석 적용) ---
def run_morning_briefing():
    print("🌅 [모닝 브리핑 기동]")
    db = get_db_client()
    if not db: return send_telegram("⚠️ [모닝 브리핑] DB 연결에 실패했습니다.")
    
    doc = db.collection('portfolios').document(USER_ID).get()
    if not doc.exists: return send_telegram(f"⚠️ <b>{USER_ID}</b>님의 포트폴리오가 없습니다.")
    
    doc_data = doc.to_dict()
    stocks = doc_data.get('stocks', [])
    if not stocks: return send_telegram(f"⚠️ <b>{USER_ID}</b>님의 포트폴리오가 비어있습니다.")
    
    portfolio_context = ""; portfolio_info_list = []; urgent_alerts = []
    krx = load_krx_data()
    
    for s in stocks:
        name = s['종목명']
        try: tck = krx[krx['Name']==name]['Code'].values[0]
        except: continue
            
        df = fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        df, ind = calculate_cloud_indicators(df)
        if ind:
            price = float(df['Close'].iloc[-1])
            prof = (price - s['매수단가']) / s['매수단가'] * 100 if s['매수단가'] > 0 else 0
            a = float(ind['ATR'])
            target = s['매수단가'] + (a*4)
            fixed_stop = s['매수단가'] - (a*2)
            
            # 💡 [Idea 1] 스마트 트레일링 스탑 로직 (수익권일 경우 익절 라인 상향)
            trailing_stop = price - (a * 2.5) 
            is_trailing_alert = False
            
            if prof > 0 and price <= trailing_stop:
                urgent_alerts.append(f"🚨 <b>[수익 보존 익절] {name}</b>: 트레일링 스탑({int(trailing_stop):,}원) 이탈! 수익을 락인(Lock-in) 하세요.")
                is_trailing_alert = True
            elif price <= fixed_stop and s['매수단가'] > 0 and not is_trailing_alert:
                urgent_alerts.append(f"🚨 <b>[긴급 손절] {name}</b>: 고정 손절가({int(fixed_stop):,}원) 이탈!")
            elif price >= target and s['매수단가'] > 0:
                urgent_alerts.append(f"🎉 <b>[목표 달성] {name}</b>: 목표가({int(target):,}원) 도달! 분할 익절 고려.")
                
            news_list = get_recent_news(name)
            portfolio_context += f"- [{name}] 수익률: {prof:.1f}%, RSI={ind.get('RSI'):.1f}, 관련뉴스: {news_list}\n"
            portfolio_info_list.append({'name': name, 'price': price, 'stop': trailing_stop if prof > 0 else fixed_stop, 'prof': prof, 'is_trailing': prof > 0})

    print("🧠 AI 뉴스 감성 및 시황 분석 중...")
    market_news = get_recent_news("글로벌 증시 마감") + get_recent_news("한국 증시 시황")
    
    # 💡 [Idea 3] 프롬프트에 '뉴스 감성 점수(Sentiment Score)' 요구 추가
    prompt = f"""
    당신은 글로벌 퀀트 전략가입니다.
    [시장뉴스]\n{market_news}\n[포트폴리오 및 개별뉴스]\n{portfolio_context}\n
    [형식]\n{{ 
        "market_overview": "오늘 장 요약(3문장)", 
        "stock_briefings": [ 
            {{"stock": "종목명", "sentiment_score": "뉴스의 호재/악재 감성 점수(0~100점)", "strategy": "대응 전략(2문장)"}} 
        ], 
        "action_plan": "핵심 지침(1문장)" 
    }}
    """
    res = get_ai_analysis(prompt)
    
    msg = f"🌅 <b>[Harness 모닝 브리핑]</b>\n\n"
    if urgent_alerts:
        msg += "⚠️ <b>[포트폴리오 긴급 액션 요망]</b>\n"
        for alert in urgent_alerts: msg += f"{alert}\n"
        msg += "\n"
        
    msg += "📊 <b>포트폴리오 상태 (트레일링 스탑 적용)</b>\n"
    for p in portfolio_info_list: 
        stop_type = "방어선(트레일링)" if p['is_trailing'] else "손절선(고정)"
        msg += f"🔹 <b>{p['name']}</b> ({p['prof']:.1f}%) 👉 🛡️{stop_type} {int(p['stop']):,}원\n"
        
    msg += f"\n🌐 <b>시장 동향</b>\n{res.get('market_overview','')}\n\n🎯 <b>종목 전략 & AI 뉴스 감성 점수</b>\n"
    for s in res.get('stock_briefings',[]): 
        msg += f"- <b>{s['stock']}</b> (감성점수: {s.get('sentiment_score','-')}점) : {s['strategy']}\n"
    send_telegram(msg)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"
    if mode == "morning": run_morning_briefing()
