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
USER_ID = os.environ.get("USER_ID", "vip")

# 💡 텔레그램 전송 함수
def send_telegram(text):
    print("▶️ 텔레그램 전송 시도 중...")
    base_url = "https://" + "api.telegram.org/bot"
    url = f"{base_url}{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
        if res.status_code != 200: print(f"🚨 텔레그램 전송 실패! 원인: {res.text}")
        else: print("✅ 텔레그램 메시지 발송 완료!")
    except Exception as e: print(f"🚨 네트워크 오류: {e}")

# --- 2. 보조 함수 (지표 계산, AI 분석) ---
def get_recent_news(keyword):
    try:
        base_url = "https://" + "news.google.com/rss/search?q="
        url = f"{base_url}{keyword}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:3] if item.title]
    except: return []

def calculate_cloud_indicators(df):
    if df is None or len(df) < 200: return None, None
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 💡 [볼린저밴드 연산 추가]
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Mid']
    
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = (100 - (100 / (1 + (gain / loss)))).fillna(50)
    
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
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
    
    # 💡 [볼린저밴드 스퀴즈 판별]
    is_squeeze = bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8) if not pd.isna(latest['BB_Width']) else False
    
    indicators = {
        "EMA15": float(latest['EMA15']),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "BB_Is_Squeeze": is_squeeze,
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']),
        "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
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
    import re
    pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', FIREBASE_JSON)
    em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', FIREBASE_JSON)
    pk_raw = FIREBASE_JSON[FIREBASE_JSON.find("-----BEGIN PRIVATE KEY-----") : FIREBASE_JSON.find("-----END PRIVATE KEY-----") + 25]
    pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
    private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
    
    token_url = "https://" + "oauth2.googleapis.com/token"
    creds_dict = {"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": token_url}
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    db = firestore.Client(credentials=creds, project=pm.group(1))
    
    doc = db.collection('portfolios').document(USER_ID).get()
    if not doc.exists:
        send_telegram("⚠️ 등록된 포트폴리오가 없습니다.")
        return
    
    doc_data = doc.to_dict()
    stocks = doc_data.get('stocks', []) if 'stocks' in doc_data else (doc_data if isinstance(doc_data, list) else [])
    realized_profit = doc_data.get('realized_profit', 0) if isinstance(doc_data, dict) else 0
    
    portfolio_context = ""
    portfolio_info_list = []
    
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
            stat = f"월봉10선={'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}, RSI={ind.get('RSI'):.1f}, MACD={'골든크로스' if ind.get('MACD_Cross') else '데드크로스'}"
            portfolio_context += f"- [{name}] 수익률: {prof:.1f}%, 지표: {stat}, 뉴스: {get_recent_news(name)}\n"
            
            a = float(ind['ATR'])
            portfolio_info_list.append({
                'name': name, 'price': price, 'stop': price - (a*2), 'target': price + (a*4), 'prof': prof
            })

    print("🧠 AI 분석 중...")
    market_news = get_recent_news("미국 증시 마감") + get_recent_news("국내 증시 시황")
    prompt = f"""
    당신은 글로벌 퀀트 전략가입니다. 아래 데이터를 바탕으로 오늘의 모닝 브리핑을 JSON으로 작성해주세요.
    * 수칙: RSI가 70 이상(과열)이면서 MACD가 데드크로스인 종목은 강력 매도를 권고하세요.
    [시장 뉴스]\n{market_news}\n[포트폴리오]\n{portfolio_context}\n
    [형식]\n{{ "market_overview": "오늘 장 요약(3문장)", "stock_briefings": [ {{"stock": "종목명", "alert_level": "🟢 안전/🟡 주의/🔴 위험", "strategy": "대응 전략(2문장)"}} ], "action_plan": "핵심 지침(1문장)" }}
    """
    res = get_ai_analysis(prompt)
    
    msg = f"🌅 <b>[Harness 모닝 브리핑]</b>\n\n"
    msg += f"💰 <b>내 가계부 현황</b>: 누적 실현손익 {int(realized_profit):,}원\n\n"
    msg += "📊 <b>내 포트폴리오 점검</b>\n"
    for p in portfolio_info_list:
        msg += f"🔹 <b>{p['name']}</b> (수익률: {p['prof']:.1f}%)\n"
        msg += f" └ 💵 현재가: {int(p['price']):,}원\n"
        msg += f" └ 🎯 목표가: {int(p['target']):,}원\n"
        msg += f" └ 🛡️ 손절가: {int(p['stop']):,}원\n\n"
    
    msg += f"🌐 <b>시장 동향</b>\n{res['market_overview']}\n\n"
    msg += "🎯 <b>종목별 전략</b>\n"
    for s in res['stock_briefings']: msg += f"- <b>{s['stock']}</b>: {s['strategy']}\n"
    msg += f"\n💡 <b>오늘의 지침:</b> {res['action_plan']}"
    
    send_telegram(msg)
    print("✅ 모닝 브리핑 루틴 완료")

# --- 4. 핵심 로직: 오후 스크리너 (오후 4시) ---
def run_afternoon_screener():
    print("🔍 [오후 타점 스크리너 기동 시작]")
    send_telegram("🔍 <b>[오후 타점 스크리너 기동 중...]</b>\n한국 우량주 중 '스퀴즈(응축)' 상태인 종목만 필터링 스캔을 시작합니다.")
    sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270", "KB금융":"105560", "POSCO홀딩스":"005490", "NAVER":"035420", "알테오젠":"196170"}
    
    res_list = []
    for n, c in sl.items():
        try:
            df = fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            p, ind = calculate_cloud_indicators(df)
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                is_macd_bullish = ind['MACD_Cross']
                is_rsi_good = (ind['RSI'] > 50) or (ind['RSI'] <= 35)
                
                # 💡 [핵심] 스퀴즈 상태인 종목만 통과시키도록 엄격한 필터링 추가!
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and is_macd_bullish and is_rsi_good and ind.get("BB_Is_Squeeze"):
                    a = float(ind['ATR'])
                    tar_p = p + (a * 4)
                    stop_p = p - (a * 2)
                    entry2 = float(ind['EMA15'])
                    rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0
                    
                    res_list.append({
                        "name": n, 
                        "sig": "🔥 강력" if sc==4 else "👍 분할", 
                        "score": sc,
                        "rules": ind["Cloud_Rules"],
                        "price": p,
                        "entry2": entry2,
                        "target": tar_p,
                        "stop": stop_p,
                        "rr_2": rr_2,
                        "rsi": ind['RSI'],
                        "macd": "골든크로스" if is_macd_bullish else "데드크로스",
                        "bb_stat": "📉스퀴즈(응축)"
                    })
            time.sleep(0.5)
        except: pass
        
    res_list.sort(key=lambda x: x['score'], reverse=True)
    
    msg = f"🚀 <b>[클라우드 스크리너 마감 보고]</b>\n\n🎯 <b>스퀴즈(응축) 발생 종목만 엄선했습니다.</b>\n총 {len(res_list)}개 타점 종목 발견!\n\n"
    for r in res_list: 
        rule_details = ", ".join([f"✅{k.split('(')[0]}" if v else f"❌{k.split('(')[0]}" for k, v in r['rules'].items()])
        
        msg += f"🔥 <b>{r['name']}</b> ({r['sig']})\n"
        msg += f" └ ☁️ <b>조건:</b> {rule_details}\n"
        msg += f" └ 📊 <b>RSI:</b> {r['rsi']:.1f} | <b>MACD:</b> {r['macd']} | <b>BB:</b> {r['bb_stat']}\n"
        msg += f" └ 🎯 <b>매수:</b> 1차 {int(r['price']):,}원 / 2차 {int(r['entry2']):,}원\n"
        msg += f" └ 🎯 <b>목표:</b> {int(r['target']):,}원\n"
        msg += f" └ 🛡️ <b>손절:</b> {int(r['stop']):,}원\n"
        msg += f" └ ⚖️ <b>손익비(매력도):</b> 2차 진입시 {r['rr_2']:.1f}배 극대화\n\n"
        
    if not res_list: msg += "월봉 10선 위 안전하며 '스퀴즈' 상태인 특급 매수 타점 종목이 오늘은 없습니다."
    
    send_telegram(msg)
    print("✅ 스크리너 루틴 완료")

# --- 5. 실행 제어 (명령어에 따라 구분) ---
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "afternoon"
    print(f"🚀 봇 실행 모드: {mode}")
    
    if mode == "morning":
        run_morning_briefing()
    elif mode == "afternoon":
        run_afternoon_screener()
    else:
        print("Usage: python bot.py [morning|afternoon]")
