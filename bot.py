import os, sys, time, json, requests
import pandas as pd
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.cloud import firestore
from google.oauth2 import service_account
import textwrap

# --- 1. 환경 변수 (GitHub Secrets에서 가져옴) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIREBASE_JSON = os.environ.get("FIREBASE_JSON")
USER_ID = os.environ.get("USER_ID", "vip") # 본인의 아이디

# 💡 [업그레이드] 에러 추적기가 탑재된 텔레그램 전송 함수
def send_telegram(text):
    print("▶️ 텔레그램 전송 시도 중...")
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
        if res.status_code != 200:
            print(f"🚨 텔레그램 전송 실패! 원인: {res.text}")
        else:
            print("✅ 텔레그램 메시지 발송 완료!")
    except Exception as e:
        print(f"🚨 네트워크 오류: {e}")

# --- 2. 보조 함수 (지표 계산, AI 분석) ---
def get_recent_news(keyword):
    try:
        url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){keyword}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:3] if item.title]
    except: return []

def calculate_cloud_indicators(df):
    if df is None or len(df) < 200: return None, None
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    recent_60 = df.tail(60)
    vol_ref_price = float(df['Close'].iloc[-1]) if recent_60['Volume'].sum() == 0 else float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
    
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['ATR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1).rolling(window=14).mean()
    
    latest = df.iloc[-1]; prev = df.iloc[-2]
    try: monthly_close = df['Close'].resample('ME').last()
    except: monthly_close = df['Close'].resample('M').last()
    current_monthly_ema10 = float(monthly_close.ewm(span=10, adjust=False).mean().iloc[-1])
    
    indicators = {
        "ATR": latest['ATR'] if not pd.isna(latest['ATR']) else latest['Close']*0.05,
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "Cloud_Rules": {
            "주가 > 200일선": bool(latest['Close'] > latest['EMA200']),
            "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']),
            "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']),
            "최대 거래량 종가 돌파": bool(latest['Close'] > vol_ref_price)
        }
    }
    return latest['Close'], indicators

def get_ai_analysis(prompt):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(res.text.replace("```json", "").replace("```", "").strip())

# --- 3. 핵심 로직: 모닝 브리핑 (아침) ---
def run_morning_briefing():
    print("🌅 [모닝 브리핑 스케줄러 기동 시작]")
    send_telegram("🌅 <b>[모닝 브리핑 스케줄러 기동 중...]</b>\n데이터를 수집하고 있습니다.")
    
    import re
    pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', FIREBASE_JSON)
    em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', FIREBASE_JSON)
    pk_raw = FIREBASE_JSON[FIREBASE_JSON.find("-----BEGIN PRIVATE KEY-----") : FIREBASE_JSON.find("-----END PRIVATE KEY-----") + 25]
    pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
    private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
    
    token_url = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
    creds_dict = {"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": token_url}
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    db = firestore.Client(credentials=creds, project=pm.group(1))
    
    doc = db.collection('portfolios').document(USER_ID).get()
    if not doc.exists:
        send_telegram("⚠️ 등록된 포트폴리오가 없습니다.")
        return
        
    stocks = doc.to_dict().get('stocks', [])
    portfolio_context = ""
    
    ticker_map = {"삼성전자":"005930", "SK하이닉스":"000660", "현대차":"005380", "기아":"000270", "LG에너지솔루션":"373220"}
    
    for s in stocks:
        name = s['종목명']
        tck = ticker_map.get(name)
        if not tck:
            try:
                krx = fdr.StockListing('KRX')
                tck = krx[krx['Name']==name]['Code'].values[0]
            except: continue
            
        df = fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        price, ind = calculate_cloud_indicators(df)
        if ind:
            prof = (price - s['매수단가']) / s['매수단가'] * 100 if s['매수단가'] > 0 else 0
            stat = f"월봉10선={'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}"
            portfolio_context += f"- [{name}] 수익률: {prof:.1f}%, 지표: {stat}, 뉴스: {get_recent_news(name)}\n"

    print("🧠 AI 분석 중...")
    market_news = get_recent_news("미국 증시 마감") + get_recent_news("국내 증시 시황")
    prompt = f"""
    당신은 글로벌 퀀트 전략가입니다. 아래 데이터를 바탕으로 오늘의 모닝 브리핑을 JSON으로 작성해주세요.
    [시장 뉴스]\n{market_news}\n[포트폴리오]\n{portfolio_context}\n
    [형식]\n{{ "market_overview": "오늘 장 요약(3문장)", "stock_briefings": [ {{"stock": "종목명", "alert_level": "🟢 안전/🟡 주의/🔴 위험", "strategy": "대응 전략(2문장)"}} ], "action_plan": "핵심 지침(1문장)" }}
    """
    res = get_ai_analysis(prompt)
    
    msg = f"🌅 <b>[Harness 모닝 브리핑]</b>\n\n🌐 <b>시장 동향</b>\n{res['market_overview']}\n\n🎯 <b>종목별 전략</b>\n"
    for s in res['stock_briefings']: msg += f"- <b>{s['stock']}</b>: {s['strategy']}\n"
    msg += f"\n💡 <b>오늘의 지침:</b> {res['action_plan']}"
    
    send_telegram(msg)
    print("✅ 모닝 브리핑 루틴 완료")

# --- 4. 핵심 로직: 오후 스크리너 (오후 4시) ---
def run_afternoon_screener():
    print("🔍 [오후 타점 스크리너 기동 시작]")
    send_telegram("🔍 <b>[오후 타점 스크리너 기동 중...]</b>\n한국 우량주 스캔을 시작합니다.")
    sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270", "KB금융":"105560", "POSCO홀딩스":"005490", "NAVER":"035420", "알테오젠":"196170"}
    
    res_list = []
    for n, c in sl.items():
        try:
            df = fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            p, ind = calculate_cloud_indicators(df)
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                    # 💡 [업그레이드] 목표가와 손절가를 함께 계산하여 메시지에 추가
                    a = float(ind['ATR'])
                    res_list.append({
                        "name": n, 
                        "sig": "🔥 강력" if sc==4 else "👍 분할", 
                        "score": sc,
                        "price": p,
                        "target": p + (a * 4),
                        "stop": p - (a * 2)
                    })
            time.sleep(0.5)
        except: pass
        
    res_list.sort(key=lambda x: x['score'], reverse=True)
    msg = f"🚀 <b>[클라우드 스크리너 마감 보고]</b>\n\n총 {len(res_list)}개 타점 종목 발견!\n\n"
    for r in res_list: 
        msg += f"<b>{r['name']}</b> ({r['sig']}) - 통과: {r['score']}/4\n"
        msg += f" └ 현재가: {int(r['price']):,}원 | 목표가: {int(r['target']):,}원 | 손절가: {int(r['stop']):,}원\n\n"
    if not res_list: msg += "월봉 10선 위 안전한 매수 타점 종목이 없습니다."
    
    send_telegram(msg)
    print("✅ 스크리너 루틴 완료")

# --- 5. 실행 제어 (명령어에 따라 구분) ---
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"🚀 봇 실행 모드: {mode}")
    
    if mode == "morning":
        run_morning_briefing()
    elif mode == "afternoon":
        run_afternoon_screener()
    else:
        print("Usage: python bot.py [morning|afternoon]")
