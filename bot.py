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

def get_db_client():
    if not FIREBASE_JSON: return None
    try:
        creds_dict = json.loads(FIREBASE_JSON, strict=False)
        if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return firestore.Client(credentials=creds, project=creds_dict.get("project_id"))
    except: return None

def get_ai_analysis(prompt, is_json=True):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    config = {"response_mime_type": "application/json"} if is_json else {}
    res = model.generate_content(prompt, generation_config=config)
    if is_json: return json.loads(res.text.replace("```json", "").replace("```", "").strip())
    return res.text.strip()

def calculate_cloud_indicators(df):
    if df is None or df.empty or len(df) < 200: return None, {}
    df = df.dropna(subset=['Close'])
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 볼린저 밴드 (스퀴즈 판별용)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Width'] = ((df['BB_Mid'] + (df['BB_Std'] * 2)) - (df['BB_Mid'] - (df['BB_Std'] * 2))) / df['BB_Mid']
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    # 수급 폭발 로직
    try:
        prev_vol_ma20 = df['Volume'].rolling(20).mean().iloc[-2]
        today_vol = df['Volume'].iloc[-1]
        is_vol_explosion = bool(prev_vol_ma20 > 0 and today_vol >= prev_vol_ma20 * 2.5)
    except:
        is_vol_explosion = False
    
    latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    indicators = {
        "EMA15": float(latest['EMA15']), "EMA5": float(latest['EMA5']),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), 
        "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8),
        "Volume_Explosion": is_vol_explosion,
        "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
        "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200'])}
    }
    return df, indicators

def get_market_top_400():
    try:
        kospi = fdr.StockListing('KOSPI')
        kospi = kospi[~kospi['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)].head(200)
        kosdaq = fdr.StockListing('KOSDAQ')
        kosdaq = kosdaq[~kosdaq['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)].head(200)
        sl = dict(zip(kospi['Name'], kospi['Code']))
        sl.update(dict(zip(kosdaq['Name'], kosdaq['Code'])))
        return sl
    except: return {"삼성전자":"005930", "SK하이닉스":"000660", "알테오젠":"196170", "에코프로비엠":"247540"}

# ==========================================
# 🌞 [모닝 브리핑] 아침 8시 30분
# ==========================================
def run_morning_briefing():
    print("🌅 [모닝 브리핑 기동]")
    db = get_db_client()
    if not db: return send_telegram("⚠️ [모닝 브리핑] DB 연결 실패")
    
    doc = db.collection('portfolios').document(USER_ID).get()
    if not doc.exists: return send_telegram(f"⚠️ <b>{USER_ID}</b>님의 포트폴리오가 없습니다.")
    
    stocks = doc.to_dict().get('stocks', [])
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
            
            trailing_stop = price - (a * 2.5) 
            is_trailing_alert = False
            
            if prof > 0 and price <= trailing_stop:
                urgent_alerts.append(f"🚨 <b>[수익 보존 익절] {name}</b>: 트레일링 스탑({int(trailing_stop):,}원) 이탈! 수익 락인 요망.")
                is_trailing_alert = True
            elif price <= fixed_stop and s['매수단가'] > 0 and not is_trailing_alert:
                urgent_alerts.append(f"🚨 <b>[긴급 손절] {name}</b>: 고정 손절가({int(fixed_stop):,}원) 이탈!")
            elif price >= target and s['매수단가'] > 0:
                urgent_alerts.append(f"🎉 <b>[목표 달성] {name}</b>: 목표가({int(target):,}원) 도달! 분할 익절 고려.")
                
            news_list = get_recent_news(name)
            portfolio_context += f"- [{name}] 수익률: {prof:.1f}%, RSI={ind.get('RSI'):.1f}, 관련뉴스: {news_list}\n"
            portfolio_info_list.append({'name': name, 'price': price, 'stop': trailing_stop if prof > 0 else fixed_stop, 'prof': prof, 'is_trailing': prof > 0})

    market_news = get_recent_news("글로벌 증시 마감") + get_recent_news("한국 증시 시황")
    prompt = f"""
    당신은 글로벌 퀀트 전략가입니다.
    [시장뉴스]\n{market_news}\n[포트폴리오 및 개별뉴스]\n{portfolio_context}\n
    [형식]\n{{ "market_overview": "오늘 장 요약(3문장)", "stock_briefings": [ {{"stock": "종목명", "sentiment_score": "뉴스의 호재/악재 감성 점수(0~100점)", "strategy": "대응 전략(2문장)"}} ], "action_plan": "핵심 지침(1문장)" }}
    """
    try:
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
        for s in res.get('stock_briefings',[]): msg += f"- <b>{s['stock']}</b> (감성점수: {s.get('sentiment_score','-')}점) : {s['strategy']}\n"
        send_telegram(msg)
    except: send_telegram("🌅 [Harness 모닝 브리핑]\nAI 분석 중 오류가 발생했습니다. 포트폴리오 점검을 직접 진행해주세요.")

# ==========================================
# ⚡ [장중 스나이퍼] 오후 1시 (S급 매수 타점 전용)
# ==========================================
def run_intraday_sniper():
    print("⚡ [장중 S급 스나이퍼 기동 시작]")
    sl = get_market_top_400()
    s_class_list = []
    
    for n, c in sl.items():
        try:
            df = fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, ind = calculate_cloud_indicators(df)
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                
                # 🏆 S급 판단 로직: 월봉10선 위 + 스퀴즈(응축) + MACD상승 + 클라우드 2개 이상
                is_squeeze = ind.get('BB_Is_Squeeze', False)
                is_macd_up = ind.get('MACD_Cross', False)
                is_safe = ind.get('Is_Above_Monthly_EMA10', False)
                is_vol_exp = ind.get('Volume_Explosion', False)
                
                if sc >= 2 and is_safe and is_squeeze and is_macd_up:
                    p = float(df['Close'].iloc[-1])
                    a = float(ind['ATR'])
                    
                    tags = []
                    if is_vol_exp: tags.append("💥수급폭발")
                    if ind['MACD_Early_Entry']: tags.append("🚀선취매")
                    else: tags.append("🟢골든크로스")
                    
                    s_class_list.append({
                        "name": n, "price": p, "target": p + (a*4), "stop": p - (a*2), 
                        "rsi": ind.get('RSI', 50), "tags": " + ".join(tags)
                    })
        except: pass
        
    if s_class_list:
        msg = "⚡ <b>[장중 S급 스나이퍼 포착]</b> ⚡\n\n"
        msg += "🏆 <b>'폭발 직전의 스프링' (스퀴즈 + MACD 상승)</b> 조건이 일치하는 특급 종목이 장중에 포착되었습니다!\n\n"
        for r in s_class_list:
            msg += f"🔥 <b>{r['name']}</b> ({r['tags']})\n"
            msg += f" └ 📊 RSI: {r['rsi']:.1f} | BB: 🚨 스퀴즈\n"
            msg += f" └ 💵 현재가: {int(r['price']):,}원\n"
            msg += f" └ 🎯 목표가: {int(r['target']):,}원\n"
            msg += f" └ 🛡️ 손절가: {int(r['stop']):,}원\n\n"
        msg += "⚠️ 장 마감 전 단기 시세 분출 가능성이 높습니다. 대시보드를 확인하세요!"
        send_telegram(msg)
    else:
        # 봇이 죽은게 아니라 포착된게 없음을 알림
        send_telegram("⚡ [장중 스캐너] 현재 시간 기준 S급(스퀴즈+MACD상승) 매수 타점 종목이 없습니다.")

# ==========================================
# 🔍 [마감 스크리너] 오후 4시 (전체 스캔 요약)
# ==========================================
def run_afternoon_screener():
    print("🔍 [마감 타점 스크리너 기동 시작]")
    sl = get_market_top_400()
    res_list = []
    
    for n, c in sl.items():
        try:
            df = fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, ind = calculate_cloud_indicators(df)
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                    p = float(df['Close'].iloc[-1])
                    a = float(ind['ATR'])
                    
                    tags = []
                    if ind.get('Volume_Explosion'): tags.append("💥수급폭발")
                    if ind['MACD_Early_Entry']: tags.append("🚀선취매")
                    if ind['RSI_Turnaround']: tags.append("📉RSI턴")
                    if ind['MACD_Cross']: tags.append("🟢골든크로스")
                    
                    res_list.append({
                        "name": n, 
                        "sig": "🔥 강력매수" if ind.get('MACD_Cross') or ind.get('MACD_Early_Entry') else "👍 분할매수", 
                        "tags": " + ".join(tags) if tags else "추세추종",
                        "price": p,
                        "target": p + (a * 4),
                        "stop": p - (a * 2)
                    })
        except: pass
        
    if not res_list:
        send_telegram("🚀 <b>[클라우드 마감 스크리너]</b>\n\n월봉 10선 위 안전한 매수 타점 종목이 없습니다.")
        return

    # 종목이 너무 많으면 강력매수(시그널) 위주로 상위 15개만 컷팅
    res_list.sort(key=lambda x: 1 if "강력" in x['sig'] else 0, reverse=True)
    top_res = res_list[:15]
    
    msg = f"🚀 <b>[클라우드 마감 스크리너]</b>\n\n총 {len(res_list)}개 타점 종목 발견! (상위 15개 요약)\n\n"
    for r in top_res: 
        msg += f"<b>{r['name']}</b> ({r['sig']})\n"
        msg += f" └ ✨ 포착원인: {r['tags']}\n"
        msg += f" └ 💵 매수대기: {int(r['price']):,}원\n"
        msg += f" └ 🎯 목표: {int(r['target']):,} / 🛡️ 손절: {int(r['stop']):,}\n\n"
        
    send_telegram(msg)

# ==========================================
# 🚦 [메인 라우터] GitHub Actions 인자값 분석
# ==========================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "afternoon"
    print(f"🚀 봇 실행 모드: {mode}")
    
    if mode == "morning":
        run_morning_briefing()
    elif mode == "intraday":
        run_intraday_sniper()
    elif mode == "afternoon":
        run_afternoon_screener()
    else:
        print("Usage: python bot.py [morning|intraday|afternoon]")
