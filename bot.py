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
        if res.status_code != 200: print(f"🚨 텔레그램 전송 실패! 원인: {res.text}")
        else: print("✅ 텔레그램 메시지 발송 완료!")
    except Exception as e: print(f"🚨 네트워크 오류: {e}")

def get_recent_news(keyword):
    try:
        base_url = "https://" + "news.google.com/rss/search?q="
        url = f"{base_url}{keyword}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:3] if item.title]
    except: return []

def load_krx_data():
    try: return fdr.StockListing('KRX')
    except: return pd.DataFrame()

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

    try:
        df = load_krx_data()
        if not df.empty and 'Market' in df.columns:
            kospi_df = df[df['Market'].str.contains('KOSPI', na=False)]
            kosdaq_df = df[df['Market'].str.contains('KOSDAQ', na=False)]
        else:
            kospi_df = fdr.StockListing('KOSPI')
            kosdaq_df = fdr.StockListing('KOSDAQ')
            
        for d in [kospi_df, kosdaq_df]:
            col = 'Code' if 'Code' in d.columns else 'Symbol'
            d[col] = d[col].astype(str).str.zfill(6)
            d = d[d[col].str.match(r'^\d{6}$')]
            d = d[~d['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
            top_stocks = dict(zip(d.head(100)['Name'], d.head(100)[col]))
            sl.update(top_stocks)
    except:
        sl.update({"삼성전자":"005930", "SK하이닉스":"000660", "알테오젠":"196170", "에코프로비엠":"247540"})
    return sl

# 💡 [정밀화 패치] MACD 선취매 & RSI 바닥 턴어라운드 로직 추가
def calculate_cloud_indicators(df):
    if df is None or df.empty or len(df) < 200: return None, {}
    df = df.dropna(subset=['Close'])
    
    # 기본 이동평균선
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 볼린저 밴드
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Width'] = ((df['BB_Mid'] + (df['BB_Std']*2)) - (df['BB_Mid'] - (df['BB_Std']*2))) / df['BB_Mid']
    
    # RSI (상대강도지수)
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    
    # MACD 및 히스토그램 
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal'] # 💡 히스토그램 추가
    
    recent_60 = df.tail(60)
    vol_ref_price = float(df['Close'].iloc[-1]) if recent_60['Volume'].sum() == 0 else float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
    
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    try: current_monthly_ema10 = float(df['Close'].resample('ME').last().ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    # 💡 [정밀 로직 1] MACD 히스토그램 선취매: 음수(하락) 구간이지만 어제보다 막대가 짧아지며 상승 준비를 하는가?
    macd_early_entry = (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist'])
    
    # 💡 [정밀 로직 2] RSI 바닥 턴어라운드: 40 이하 과매도권에서 고개를 들기 시작했는가?
    rsi_turnaround = (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI'])
    
    indicators = {
        "EMA15": float(latest['EMA15']), "EMA5": float(latest['EMA5']),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8) if not pd.isna(latest['BB_Width']) else False,
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), 
        "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "MACD_Early_Entry": macd_early_entry, # 추가됨
        "RSI_Turnaround": rsi_turnaround,     # 추가됨
        "Cloud_Rules": {
            "주가 > 200일선": bool(latest['Close'] > latest['EMA200']),
            "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']),
            "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']),
            "최대 거래량 종가 돌파": bool(latest['Close'] > vol_ref_price)
        },
        "Volume_Surge": bool(latest['Volume'] > prev['Volume'] * 3)
    }
    return df, indicators

def get_ai_analysis(prompt, is_json=True):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    config = {"response_mime_type": "application/json"} if is_json else {}
    res = model.generate_content(prompt, generation_config=config)
    if is_json: return json.loads(res.text.replace("```json", "").replace("```", "").strip())
    return res.text.strip()

# 이중 안전망 DB 클라이언트
def get_db_client():
    if not FIREBASE_JSON: return None
    try:
        creds_dict = json.loads(FIREBASE_JSON, strict=False)
        if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return firestore.Client(credentials=creds, project=creds_dict.get("project_id"))
    except Exception as e1:
        try:
            pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', FIREBASE_JSON)
            em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', FIREBASE_JSON)
            pk_raw = FIREBASE_JSON[FIREBASE_JSON.find("-----BEGIN PRIVATE KEY-----") : FIREBASE_JSON.find("-----END PRIVATE KEY-----") + 25]
            pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
            private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
            creds_dict = {"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": "https://oauth2.googleapis.com/token"}
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds, project=pm.group(1))
        except: return None

# --- 1. 아침 모닝 브리핑 ---
def run_morning_briefing():
    print("🌅 [모닝 브리핑 기동]")
    db = get_db_client()
    if not db: return send_telegram("⚠️ [모닝 브리핑] DB 연결에 실패했습니다.")
    
    doc = db.collection('portfolios').document(USER_ID).get()
    if not doc.exists: return send_telegram(f"⚠️ [모닝 브리핑] 등록된 포트폴리오가 없습니다.")
    
    doc_data = doc.to_dict()
    stocks = doc_data.get('stocks', []) if 'stocks' in doc_data else (doc_data if isinstance(doc_data, list) else [])
    realized_profit = doc_data.get('realized_profit', 0) if isinstance(doc_data, dict) else 0
    
    if not stocks: return send_telegram(f"⚠️ [모닝 브리핑] 보유 중인 종목이 없습니다. 현금 100% 상태입니다.")
    
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
            target = s['매수단가'] + (a*4); stop = s['매수단가'] - (a*2)
            
            if price <= stop and s['매수단가'] > 0: urgent_alerts.append(f"🚨 <b>[긴급 손절] {name}</b>: 손절가 이탈!")
            elif price >= target and s['매수단가'] > 0: urgent_alerts.append(f"🎉 <b>[목표 달성] {name}</b>: 목표가 도달!")
                
            stat = f"RSI={ind.get('RSI'):.1f}, MACD={'선취매 구간' if ind.get('MACD_Early_Entry') else ('골든' if ind.get('MACD_Cross') else '데드')}"
            portfolio_context += f"- [{name}] 수익률: {prof:.1f}%, 지표: {stat}, 뉴스: {get_recent_news(name)}\n"
            portfolio_info_list.append({'name': name, 'price': price, 'stop': stop, 'target': target, 'prof': prof})

    market_news = get_recent_news("미국 증시 마감") + get_recent_news("국내 증시 시황")
    prompt = f"당신은 글로벌 퀀트 전략가입니다.\n[뉴스]\n{market_news}\n[포트폴리오]\n{portfolio_context}\n[형식]\n{{ \"market_overview\": \"오늘 장 요약(3문장)\", \"stock_briefings\": [ {{\"stock\": \"종목명\", \"alert_level\": \"🟢 안전/🟡 주의/🔴 위험\", \"strategy\": \"대응 전략(2문장)\"}} ], \"action_plan\": \"핵심 지침(1문장)\" }}"
    res = get_ai_analysis(prompt)
    
    msg = f"🌅 <b>[Harness 모닝 브리핑]</b>\n\n"
    if urgent_alerts:
        msg += "⚠️ <b>[긴급 액션 요망]</b>\n"
        for alert in urgent_alerts: msg += f"{alert}\n"
        msg += "\n"
        
    msg += f"💰 <b>내 가계부</b>: 누적 실현손익 {int(realized_profit):,}원\n\n📊 <b>포트폴리오 상태</b>\n"
    for p in portfolio_info_list: msg += f"🔹 <b>{p['name']}</b> ({p['prof']:.1f}%)\n └ 현재 {int(p['price']):,}원 / 🎯목표 {int(p['target']):,}원 / 🛡️손절 {int(p['stop']):,}원\n"
    msg += f"\n🌐 <b>시장 동향</b>\n{res.get('market_overview','')}\n\n🎯 <b>종목 전략</b>\n"
    for s in res.get('stock_briefings',[]): msg += f"- <b>{s['stock']}</b>: {s['strategy']}\n"
    send_telegram(msg)

# --- 2. 장중 스크리너 로직 ---
def run_intraday_screener():
    print("⚡ [장중 폭발 스크리너 기동]")
    db = get_db_client()
    sl = get_screener_target_stocks(db)
    
    res_list = []
    for n, c in sl.items():
        try:
            df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=300)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
            if ind and ind.get('Volume_Surge'): 
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                    res_list.append({"name": n, "price": float(df['Close'].iloc[-1]), "rsi": ind['RSI']})
            time.sleep(0.3)
        except: pass
        
    if res_list:
        msg = "⚡ <b>[긴급 장중 수급 폭발 포착]</b>\n어제 대비 거래량이 300% 이상 터진 타점 종목입니다!\n\n"
        for r in res_list: msg += f"🔥 <b>{r['name']}</b> (현재가: {int(r['price']):,}원 / RSI: {r['rsi']:.1f})\n"
        send_telegram(msg)

# --- 3. 마감 스크리너 (정밀화 로직 적용) ---
def run_afternoon_screener():
    print("🔍 [오후 타점 스크리너 기동 - 정밀화 엔진]")
    db = get_db_client()
    sl = get_screener_target_stocks(db)
    
    res_list = []
    for i, (n, c) in enumerate(sl.items()):
        try:
            df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=300)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                
                # 💡 [정밀 필터링 적용] 
                # 조건 1: 클라우드 기본 점수 2 이상 + 월봉 안전권
                # 조건 2: (MACD 선취매 턴어라운드) OR (RSI 바닥 턴어라운드) OR (기본 MACD 골든크로스)
                is_smart_entry = ind['MACD_Early_Entry'] or ind['RSI_Turnaround'] or ind['MACD_Cross']
                
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and is_smart_entry:
                    p = float(df['Close'].iloc[-1])
                    a = float(ind['ATR'])
                    
                    # 어떤 시그널로 잡혔는지 태그 달기
                    sig_tags = []
                    if ind['MACD_Early_Entry']: sig_tags.append("🚀MACD선취매")
                    if ind['RSI_Turnaround']: sig_tags.append("📉RSI턴어라운드")
                    if ind['MACD_Cross']: sig_tags.append("🟢정통골든크로스")
                    
                    res_list.append({
                        "name": n, "sig": "🔥 강력" if sc>=3 else "👍 분할", "score": sc,
                        "price": p, "entry1": ind['EMA5'] if p > ind['EMA5'] else p,
                        "target": (ind['EMA5'] if p > ind['EMA5'] else p) + (a * 4), "stop": (ind['EMA5'] if p > ind['EMA5'] else p) - (a * 2),
                        "rsi": ind['RSI'], "tags": " + ".join(sig_tags), "is_squeeze": ind.get("BB_Is_Squeeze", False)
                    })
            time.sleep(0.3)
        except: pass
        
    res_list.sort(key=lambda x: (x['is_squeeze'], x['score']), reverse=True)
    
    msg = f"🚀 <b>[클라우드 스크리너 마감 보고]</b>\n총 {len(res_list)}개 타점 발견\n\n"
    found_stock_names = []
    for r in res_list: 
        found_stock_names.append(r['name'])
        bb_stat = "🚨스퀴즈🚨" if r['is_squeeze'] else "확장"
        info = f"<b>{r['name']}</b> ({r['sig']}) | RSI:{r['rsi']:.1f} | {bb_stat}\n"
        info += f" └ ✨ <b>포착원인:</b> {r['tags']}\n"
        info += f" └ 🎯 <b>매수대기:</b> {int(r['entry1']):,}원 (현재 {int(r['price']):,}원)\n"
        info += f" └ 🎯 <b>목표:</b> {int(r['target']):,}원 / 🛡️ <b>손절:</b> {int(r['stop']):,}원\n\n"
        if len(msg) + len(info) > 3500:
            send_telegram(msg); time.sleep(0.5); msg = info
        else: msg += info
        
    if not res_list: msg += "안전한 스마트 매수 타점 종목이 오늘은 없습니다."
    send_telegram(msg)
    
    if found_stock_names:
        print("🧠 테마 요약 AI 분석 중...")
        theme_prompt = f"오늘 퀀트 검색기에 포착된 종목들입니다: {', '.join(found_stock_names)}\n위 종목들을 보고 현재 한국 시장의 수급이 어떤 섹터나 테마로 쏠리고 있는지 3~4줄로 분석하여 브리핑해주세요. (평문으로 응답)"
        theme_summary = get_ai_analysis(theme_prompt, is_json=False)
        send_telegram(f"💡 <b>[AI 주도 테마 요약]</b>\n\n{theme_summary}")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "afternoon"
    print(f"🚀 봇 실행 모드: {mode}")
    
    if mode == "morning": run_morning_briefing()
    elif mode == "intraday": run_intraday_screener()
    elif mode == "afternoon": run_afternoon_screener()
    else: print("Usage: python bot.py [morning|intraday|afternoon]")
