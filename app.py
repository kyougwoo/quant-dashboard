import streamlit as st
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np
import os
import time
import re
import textwrap

# 💡 Firebase 클라우드 DB 연결
FIREBASE_IMPORT_ERROR = ""
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError as e:
    FIREBASE_AVAILABLE = False
    FIREBASE_IMPORT_ERROR = str(e)

st.set_page_config(page_title="클라우드 퀀트 PRO", layout="wide", page_icon="☁️", initial_sidebar_state="collapsed")

# 💎 [10점 만점 패치] 최고급 다크 테마 & 메신저 UI CSS 적용
st.markdown("""
<style>
    /* 기본 배경 및 여백 설정 */
    .stApp { background-color: #0f172a; color: #f8fafc; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {background-color: transparent !important;}
    @media (max-width: 768px) { .block-container { padding: 2rem 0.5rem !important; } h1 { font-size: 1.5rem !important; } }
    
    /* 럭셔리 타이틀 */
    .main-title { font-size: 2.2rem; font-weight: 900; background: -webkit-linear-gradient(45deg, #38bdf8, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px; }
    .title-by { font-size: 0.4em; color: #cbd5e1; font-weight: 600; vertical-align: super; margin-left: 10px; background-color: #1e293b; padding: 4px 10px; border-radius: 12px; border: 1px solid #334155; letter-spacing: 1px; -webkit-text-fill-color: #cbd5e1; }
    
    /* 입체형 프리미엄 KPI 카드 */
    .kpi-card { background: linear-gradient(145deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 16px; padding: 20px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); transition: transform 0.2s; height: 100%; }
    .kpi-card:hover { transform: translateY(-5px); border-color: #38bdf8; }
    .kpi-title { font-size: 0.9rem; color: #94a3b8; font-weight: 700; letter-spacing: 1px; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }
    .kpi-value-main { font-size: 1.8rem; font-weight: 900; color: #f8fafc; margin-bottom: 5px; }
    .kpi-value-sub { font-size: 1rem; color: #94a3b8; font-weight: 500; }
    .kpi-highlight { color: #34d399; }
    .kpi-danger { color: #f87171; }
    .kpi-divider { height: 1px; background: #334155; margin: 15px 0; }
    
    /* 4-Agent 대화형 메신저 말풍선 */
    .chat-container { display: flex; flex-direction: column; gap: 15px; margin-top: 10px; animation: fadeIn 0.8s ease-out forwards; }
    .chat-bubble { padding: 18px 24px; border-radius: 16px; color: #f8fafc; background-color: #1e293b; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 5px solid; position: relative; }
    .chat-macro { border-color: #38bdf8; } 
    .chat-tech { border-color: #34d399; } 
    .chat-funda { border-color: #fbbf24; } 
    .chat-risk { border-color: #ef4444; background: linear-gradient(to right, #451a1a, #1e293b); } 
    .chat-header { font-weight: 800; margin-bottom: 12px; font-size: 1.1em; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }
    .score-badge { background: #0f172a; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; color: #38bdf8; border: 1px solid #1e293b; }
    .score-badge-risk { background: #7f1d1d; color: #fca5a5; border-color: #991b1b; font-size: 1em; padding: 6px 14px;}
    
    /* 애니메이션 */
    @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
    
    /* 🛠️ [가독성 완벽 패치 2탄] 버튼 스타일링 */
    .stButton > button { 
        border-radius: 12px !important; 
        font-weight: 800 !important; 
        letter-spacing: 0.5px; 
        transition: all 0.3s; 
        background-color: #1e293b !important; 
        color: #f8fafc !important; 
        border: 1px solid #38bdf8 !important; 
    }
    .stButton > button p { color: inherit !important; }
    .stButton > button:hover { 
        background-color: #38bdf8 !important; 
        color: #0f172a !important; 
        border-color: #38bdf8 !important; 
    }
    .stButton > button:focus {
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.5) !important;
        color: #f8fafc !important;
    }
    
    /* 🛠️ [가독성 완벽 패치 1탄] 폼, 입력창 색상 고정 */
    label[data-testid="stWidgetLabel"] p { color: #cbd5e1 !important; font-weight: 600 !important; }
    .stTextInput input, .stNumberInput input { background-color: #1e293b !important; color: #f8fafc !important; border: 1px solid #334155 !important; }
    div[data-baseweb="select"] > div { background-color: #1e293b !important; color: #f8fafc !important; border: 1px solid #334155 !important; }
    div[data-baseweb="select"] span { color: #f8fafc !important; }
    ul[data-baseweb="menu"] { background-color: #1e293b !important; }
    li[data-baseweb="menu-item"] { color: #f8fafc !important; background-color: #1e293b !important; }
    li[data-baseweb="menu-item"]:hover { background-color: #334155 !important; }
    div[data-testid="stExpander"] details summary { background-color: #1e293b !important; color: #f8fafc !important; border: 1px solid #334155 !important; border-radius: 8px !important; }
    div[data-testid="stExpander"] details summary p { color: #f8fafc !important; font-weight: 700 !important; }
    button[data-baseweb="tab"] p { color: #94a3b8 !important; font-weight: 600 !important; }
    button[data-baseweb="tab"][aria-selected="true"] p { color: #38bdf8 !important; font-weight: 800 !important; }
    div[data-testid="stCheckbox"] p, div[data-testid="stRadio"] p { color: #f8fafc !important; }
    .stTextInput input:focus, .stNumberInput input:focus, div[data-baseweb="select"] > div:focus-within { border-color: #38bdf8 !important; box-shadow: 0 0 0 1px #38bdf8 !important; }
</style>
""", unsafe_allow_html=True)

def init_db():
    if not FIREBASE_AVAILABLE: return None, f"🚨 라이브러리 누락: {FIREBASE_IMPORT_ERROR}"
    try:
        raw_s = str(st.secrets.get("FIREBASE_JSON", st.secrets.get("firebase", "")))
        if not raw_s: return None, "❌ 설정창(Secrets) 비어있음."
        pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', raw_s)
        em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', raw_s)
        pk_raw = raw_s[raw_s.find("-----BEGIN PRIVATE KEY-----") : raw_s.find("-----END PRIVATE KEY-----") + 25]
        pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
        private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
        creds = service_account.Credentials.from_service_account_info({"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": "https://oauth2.googleapis.com/token"})
        return firestore.Client(credentials=creds, project=pm.group(1)), "✅ 연결 성공"
    except Exception as e: return None, f"❌ 접속 거부: {e}"

if 'db_client' not in st.session_state:
    st.session_state.db_client, st.session_state.db_msg = init_db()
db = st.session_state.db_client

for k in ['logged_in', 'user_id', 'user_tier']:
    if k not in st.session_state: st.session_state[k] = False if k == 'logged_in' else 'guest' if k == 'user_id' else 'Free'
if 'invest_style' not in st.session_state: st.session_state.invest_style = "⚖️ 보통 (균형 추구)"

# 💡 상단 계정 및 환경 설정
st.markdown("<h1 class='main-title'>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#94a3b8; margin-bottom: 25px;'>전문가용 다중 지표 차트 & LLM 기반 자동화 자산운용 대시보드</p>", unsafe_allow_html=True)

with st.expander("👤 계정 및 봇(Bot) 설정", expanded=not st.session_state.logged_in):
    acc_col, set_col = st.columns([1, 1])
    with acc_col:
        st.markdown("### 👤 계정 관리")
        if not st.session_state.logged_in:
            login_id = st.text_input("아이디 (이메일)")
            login_pw = st.text_input("비밀번호", type="password")
            if st.button("로그인 / 회원가입", use_container_width=True):
                if login_id and login_pw:
                    if db:
                        try:
                            user_ref = db.collection('users').document(login_id)
                            user_doc = user_ref.get()
                            if user_doc.exists and user_doc.to_dict().get('password') == login_pw:
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, user_doc.to_dict().get('tier', 'Free')
                            elif not user_doc.exists:
                                tier = 'VIP' if login_id.lower() == 'vip' else 'Free'
                                user_ref.set({'password': login_pw, 'tier': tier, 'created_at': datetime.now()})
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, tier
                            st.rerun()
                        except: st.error("DB 오류")
                    else:
                        st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, 'VIP' if login_id == 'vip' else 'Free'; st.rerun()
        else:
            st.success(f"환영합니다, **{st.session_state.user_id}**님! (등급: {st.session_state.user_tier})")
            if st.button("로그아웃", use_container_width=True):
                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = False, 'guest', 'Free'; st.rerun()
                
    with set_col:
        st.markdown("### ⚙️ 시스템 설정")
        st.session_state.invest_style = st.selectbox("🎯 AI 성향 타겟팅", ["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"], index=["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"].index(st.session_state.invest_style))
        gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if not gemini_api_key: gemini_api_key = st.text_input("Gemini API Key (필수)", type="password")
        tele_token = str(st.secrets.get("TELEGRAM_TOKEN", "")).strip()
        tele_chat_id = ""
        
        if st.session_state.logged_in and db:
            user_ref = db.collection('users').document(st.session_state.user_id)
            tele_chat_id = user_ref.get().to_dict().get('telegram_chat_id', "") if user_ref.get().exists else ""
            input_chat_id = st.text_input("📱 텔레그램 Chat ID", value=tele_chat_id)
            if input_chat_id != tele_chat_id and st.button("알림 ID 저장"):
                user_ref.update({'telegram_chat_id': input_chat_id}); st.success("저장 완료!"); time.sleep(1); st.rerun()
            tele_chat_id = input_chat_id

st.markdown("---")

def send_telegram_message(token, chat_id, text):
    try: return requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5).status_code == 200
    except: return False

def load_portfolio():
    default_data = {'initial_capital': 0, 'realized_profit': 0, 'stocks': []}
    if db:
        try:
            doc = db.collection('portfolios').document(st.session_state.user_id).get()
            if doc.exists:
                data = doc.to_dict()
                if 'stocks' in data and 'initial_capital' not in data:
                    return {'initial_capital': 0, 'realized_profit': 0, 'stocks': data['stocks']}
                return data
        except: pass
    file_name = f'portfolio_data_{st.session_state.user_id}.json'
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r') as f: return json.load(f)
        except: pass
    return default_data

def save_portfolio(data):
    if db:
        try: db.collection('portfolios').document(st.session_state.user_id).set(data); return
        except: pass
    with open(f'portfolio_data_{st.session_state.user_id}.json', 'w') as f:
        json.dump(data, f)

if 'p_data' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.p_data, st.session_state.current_user = load_portfolio(), st.session_state.user_id

@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip().upper()
    if not query: return None, None
    try:
        df_krx = fdr.StockListing('KRX')
        df_krx['Name_NoSpace'] = df_krx['Name'].str.replace(" ", "").str.upper()
        if query.isdigit() and len(query) == 6:
            match = df_krx[df_krx['Code'] == query]
            if not match.empty: return match['Name'].values[0], query
        query_nospace = query.replace(" ", "")
        match = df_krx[df_krx['Name_NoSpace'] == query_nospace]
        if not match.empty: return match['Name'].values[0], match['Code'].values[0]
        match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query_nospace, na=False)]
        if not match_partial.empty: 
            best = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]
            return best['Name'], best['Code']
    except: pass
    if re.match(r'^[A-Z0-9\.]+$', query): return query, query
    return None, None

@st.cache_data(ttl=86400)
def get_financial_summary(ticker):
    if not str(ticker).isdigit(): return "해외주식은 기본적 분석 대신 기술적 지표에 집중합니다."
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        per = soup.select_one('#_per').text if soup.select_one('#_per') else "N/A"
        pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else "N/A"
        return f"PER: {per} / PBR: {pbr}"
    except: return "수집 오류"

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        df = fdr.StockListing('KOSPI')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except: return {"삼성전자":"005930", "SK하이닉스":"000660"}

@st.cache_data(ttl=86400)
def get_us_top_stocks():
    try:
        df = fdr.StockListing('S&P500')
        return dict(zip(df.head(100)['Name'], df.head(100)['Symbol']))
    except: return {"Apple":"AAPL", "Tesla":"TSLA", "NVIDIA":"NVDA"}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    try:
        res = requests.get(f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko", timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:5] if item.title]
    except: return ["뉴스 수집 오류"]

def format_price(price, ticker):
    return f"{int(price):,}원" if str(ticker).isdigit() else f"${price:,.2f}"

@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    for attempt in range(5):
        try:
            res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            text = res.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            if attempt < 4: time.sleep(2); continue
            raise e

def calculate_cloud_indicators(df):
    if df is None or df.empty: return None, {}
    df = df[~df.index.duplicated(keep='first')] 
    df = df.dropna(subset=['Close'])
    if len(df) < 200: return None, {}
    
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Mid']
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    recent_60 = df.tail(60)
    df['Vol_Ref_Price'] = float(df['Close'].iloc[-1]) if recent_60['Volume'].sum() == 0 else float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
    
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift(1)).abs()
    low_close = (df['Low'] - df['Close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest, prev = df.iloc[-1], df.iloc[-2]
    is_squeeze = bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8) if not pd.isna(latest['BB_Width']) else False
    
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']), "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "BB_Upper": float(latest['BB_Upper']) if not pd.isna(latest['BB_Upper']) else 0.0, "BB_Lower": float(latest['BB_Lower']) if not pd.isna(latest['BB_Lower']) else 0.0, "BB_Is_Squeeze": is_squeeze,
        "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), "MACD": float(latest['MACD']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']), "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']), "최대 거래량 종가 돌파": bool(latest['Close'] > latest['Vol_Ref_Price'])}
    }
    return df, indicators

def run_backtest_with_markers(df):
    trades = []; position = 0; entry_price = 0; entry_atr = 0; balance = 10000000 
    buy_dates=[]; buy_prices=[]; sell_dates=[]; sell_prices=[]
    
    if df is None or df.empty: 
        return {'total_trades': 0, 'win_rate': 0, 'total_return': 0}, {'x': buy_dates, 'y': buy_prices}, {'x': sell_dates, 'y': sell_prices}
        
    for i in range(1, len(df)):
        prev, curr, date = df.iloc[i-1], df.iloc[i], df.index[i]
        if pd.isna(curr['EMA200']): continue
        if position == 0:
            if prev['EMA5'] <= prev['EMA15'] and curr['EMA5'] > curr['EMA15'] and curr['Close'] > curr['EMA200']:
                position = 1; entry_price = curr['Close']; entry_atr = curr['ATR'] if not pd.isna(curr['ATR']) and curr['ATR']>0 else curr['Close']*0.05
                trades.append({'type': 'BUY'}); buy_dates.append(date); buy_prices.append(entry_price)
        elif position == 1:
            stop_loss = entry_price - (entry_atr * 2); target = entry_price + (entry_atr * 4); sell_price = 0
            if curr['Low'] <= stop_loss: sell_price = stop_loss
            elif curr['High'] >= target: sell_price = target
            elif prev['EMA5'] >= prev['EMA15'] and curr['EMA5'] < curr['EMA15']: sell_price = curr['Close']
            
            if sell_price > 0:
                position = 0; profit_pct = (sell_price - entry_price) / entry_price; balance *= (1 + profit_pct)
                trades.append({'type': 'SELL', 'profit_pct': profit_pct * 100})
                sell_dates.append(date); sell_prices.append(sell_price)
                
    sells = [t for t in trades if t['type'] == 'SELL']
    wins = [t for t in sells if t['profit_pct'] > 0]
    stats = {'total_trades': len(sells), 'win_rate': (len(wins)/len(sells)*100) if sells else 0, 'total_return': ((balance-10000000)/10000000)*100}
    return stats, {'x': buy_dates, 'y': buy_prices}, {'x': sell_dates, 'y': sell_prices}

# 💡 [핵심 버그 수정] 이전에 누락되었던 현재가 조회 함수 복구!
@st.cache_data(ttl=3600)
def get_current_price(ticker):
    try:
        df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        return float(df['Close'].iloc[-1]) if not df.empty else 0.0
    except: return 0.0

col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "알테오젠", "애플(AAPL)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (영문 코드 가능)", "삼성전자")
    else: stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search; st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)

# 🎨 탭 스타일링
tab1, tab2, tab3 = st.tabs(["📊 프로 차트 분석", "💼 포트폴리오 관리", "📡 프리미엄 스크리너"])

# -----------------------------------------------------
# [탭 1] 차트 & 타점 분석 (TradingView 스타일 적용)
# -----------------------------------------------------
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: 
        st.error("❌ 종목을 찾을 수 없습니다. (이름이나 코드를 다시 확인해 주세요)")
        st.stop()

    st.markdown(f"<h3 style='color: #f8fafc;'>📊 {actual_name} <span style='font-size: 0.6em; color: #64748b;'>{ticker}</span></h3>", unsafe_allow_html=True)
    with st.spinner("터미널 데이터 동기화 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) 
        except: 
            df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) 
        
        # 💎 [10점 만점 패치] TradingView 다크 테마 플롯리 (Plotly Dark)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        
        # Row 1: 주가 및 보조지표 (네온 컬러)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Upper'], mode='lines', line=dict(color='rgba(56, 189, 248, 0.5)', width=1), name='BB 상단'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Lower'], mode='lines', line=dict(color='rgba(56, 189, 248, 0.5)', width=1), fill='tonexty', fillcolor='rgba(56, 189, 248, 0.05)', name='BB 하단'), row=1, col=1)
        
        # 캔들스틱 (청록 상승, 빨강 하락)
        fig.add_trace(go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#06b6d4', width=1.5), name='5일선(단기)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선(지지)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선(추세)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='#ef4444', width=2, dash='dash'), name='최대 매물대'), row=1, col=1)
        
        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]; b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]; s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', color='#34d399', size=14, line=dict(width=1, color='#1e293b')), name='시스템 매수'), row=1, col=1)
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', color='#f87171', size=14, line=dict(width=1, color='#1e293b')), name='시스템 매도'), row=1, col=1)

        # Row 2: 거래량
        colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for _, row in display_df.iterrows()]
        fig.add_trace(go.Bar(x=display_df.index, y=display_df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

        curr_price = float(df['Close'].iloc[-1])
        formatted_price = f"{int(curr_price):,}원" if str(ticker).isdigit() else f"${curr_price:,.2f}"
        fig.add_hline(y=curr_price, line_dash="dot", line_color="#38bdf8", line_width=1.5, annotation_text=f"현재가: {formatted_price}", annotation_position="right", annotation_font=dict(size=12, color="white"), annotation_bgcolor="#0284c7", row=1, col=1)

        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False,
            height=650, margin=dict(l=10, r=80, t=10, b=20), 
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(size=11, color="#cbd5e1")),
            hovermode="x unified",
            xaxis=dict(showgrid=True, gridcolor='#334155'), yaxis=dict(showgrid=True, gridcolor='#334155'),
            xaxis2=dict(showgrid=True, gridcolor='#334155'), yaxis2=dict(showgrid=True, gridcolor='#334155')
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True, 'modeBarButtonsToRemove': ['lasso2d', 'select2d'], 'displaylogo': False})

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

        # 💎 [10점 만점 패치] 밋밋한 텍스트 대신 '입체형 프리미엄 KPI 카드' 적용
        curr_p = float(df['Close'].iloc[-1])
        ema5 = float(tech_ind['EMA5'])
        entry2 = float(tech_ind['EMA15'])
        entry1 = ema5 if curr_p > ema5 else curr_p
        tar_p = entry1 + (float(tech_ind['ATR']) * 4)
        stop_p = entry1 - (float(tech_ind['ATR']) * 2)
        rr_1 = (tar_p - entry1) / (entry1 - stop_p) if (entry1 - stop_p) > 0 else 0
        rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0

        is_chasing = curr_p > ema5 * 1.02
        chasing_warning = "<span style='color:#f87171; font-size:0.8em; border: 1px solid #f87171; padding: 2px 6px; border-radius: 6px; margin-left: 10px;'>🚨 추격매수 주의</span>" if is_chasing else ""

        html_kpi = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px;">
            <div class="kpi-card">
                <div class="kpi-title">🎯 스마트 대기 타점 (눌림목) {chasing_warning}</div>
                <div class="kpi-value-main kpi-highlight">1차: {format_price(entry1, ticker)}</div>
                <div class="kpi-value-sub">2차: {format_price(entry2, ticker)} (15일선 지지)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">🛡️ 자동 산출 목표 & 손절 라인</div>
                <div class="kpi-value-main" style="color: #60a5fa;">목표가: {format_price(tar_p, ticker)}</div>
                <div class="kpi-value-sub kpi-danger">손절가: {format_price(stop_p, ticker)}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">⚖️ 터틀 손익비 (RR Ratio)</div>
                <div class="kpi-value-main" style="color: #fbbf24;">1차 진입시: {rr_1:.1f}배</div>
                <div class="kpi-value-sub">2차 진입시: {rr_2:.1f}배 (극대화)</div>
            </div>
        </div>
        """
        st.markdown(html_kpi, unsafe_allow_html=True)

        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>☁️ 클라우드 4원칙</h4>", unsafe_allow_html=True)
            if tech_ind:
                for rule, passed in tech_ind["Cloud_Rules"].items(): 
                    icon = "✅" if passed else "❌"
                    color = "#34d399" if passed else "#64748b"
                    st.markdown(f"<span style='color: {color}; font-weight: 500;'>{icon} {rule}</span>", unsafe_allow_html=True)
                
                rsi_val = tech_ind.get('RSI', 50)
                rsi_color = "#f87171" if rsi_val >= 70 else "#38bdf8" if rsi_val <= 30 else "#cbd5e1"
                macd_cross = "🟢 골든크로스(매수)" if tech_ind.get('MACD_Cross') else "🔴 데드크로스(매도)"
                bb_sig = "📉 스퀴즈 (응축 폭발전야!)" if tech_ind.get('BB_Is_Squeeze') else "📈 일반 확장"
                
                st.markdown(f"""
                <div style='background: #1e293b; padding: 15px; border-radius: 12px; margin-top: 15px; border-left: 4px solid #3b82f6;'>
                    <div style='margin-bottom: 8px;'><b>RSI (14):</b> <span style='color: {rsi_color}; font-weight: bold;'>{rsi_val:.1f}</span></div>
                    <div style='margin-bottom: 8px;'><b>MACD:</b> {macd_cross}</div>
                    <div><b>볼린저밴드:</b> <span style='color: #fbbf24;'>{bb_sig}</span></div>
                </div>
                """, unsafe_allow_html=True)
                
                if tech_ind.get('Is_Above_Monthly_EMA10'): 
                    st.markdown(f"<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(52, 211, 153, 0.1); color: #34d399; font-weight: 600;'>🟢 월봉 10선 생명선 위 (안전구간)</div>", unsafe_allow_html=True)
                else: 
                    st.markdown(f"<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(248, 113, 113, 0.1); color: #f87171; font-weight: 600;'>🔴 월봉 10선 생명선 이탈 (위험구간)</div>", unsafe_allow_html=True)
            
        with info_col2:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>📰 실시간 마켓 내러티브</h4>", unsafe_allow_html=True)
            news_html = "<div style='display: flex; flex-direction: column; gap: 10px;'>"
            for news in get_recent_news(actual_name)[:4]: 
                news_html += f"<div style='background: #1e293b; padding: 12px 15px; border-radius: 8px; font-size: 0.9em; color: #cbd5e1; border-left: 3px solid #64748b;'>{news}</div>"
            news_html += "</div>"
            st.markdown(news_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("<h3 style='color: #38bdf8;'>🤖 Harness 4-Agent 분석 엔진</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #94a3b8; font-size: 0.9em;'>거시/기술/기본적 에이전트와 리스크 관리자가 <b>'{st.session_state.invest_style}'</b> 성향에 맞춰 최종 회의를 진행합니다.</p>", unsafe_allow_html=True)
        
        if st.button("🚀 4-Agent 회의 소집 (분석 실행)", type="primary", use_container_width=True):
            if not gemini_api_key: st.error("위쪽 시스템 설정에서 API Key를 입력하세요!"); st.stop()
            with st.spinner("4명의 AI 전문가가 차트와 뉴스를 분석하며 토론 중입니다... (약 10초 소요)"):
                prompt = f"""
                당신은 'Harness 4-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다. 성향: {st.session_state.invest_style}
                종목: {actual_name}, 뉴스: {get_recent_news(actual_name)[:3]}, 월봉10선: {'안전' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험'}
                RSI: {tech_ind['RSI']:.1f}, MACD: {'골든크로스' if tech_ind['MACD_Cross'] else '데드크로스'}, 손절가: {format_price(stop_p, ticker)}
                RSI 70 이상 및 MACD 데드크로스 시 강력 매도 권고. 출력 형식(JSON): {{"macroAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "technicalAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "fundamentalAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "riskManager": {{"action": "매수/관망/매도", "positionSize": "비중", "reasoning": "..."}}}}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    
                    # 💎 [10점 만점 패치] 세련된 대화형 말풍선(Chat Bubble) UI로 출력
                    html_chat = f"""
                    <div class="chat-container">
                        <div class="chat-bubble chat-macro">
                            <div class="chat-header"><span>🌍 Agent 1: 거시경제 전략가</span> <span class="score-badge">Score: {res['macroAgent']['score']}/100</span></div>
                            <div style="line-height: 1.6;">{res['macroAgent']['reasoning']}</div>
                        </div>
                        <div class="chat-bubble chat-tech">
                            <div class="chat-header"><span>📈 Agent 2: 기술적 분석가</span> <span class="score-badge">Score: {res['technicalAgent']['score']}/100</span></div>
                            <div style="line-height: 1.6;">{res['technicalAgent']['reasoning']}</div>
                        </div>
                        <div class="chat-bubble chat-funda">
                            <div class="chat-header"><span>📰 Agent 3: 펀더멘털 매니저</span> <span class="score-badge">Score: {res['fundamentalAgent']['score']}/100</span></div>
                            <div style="line-height: 1.6;">{res['fundamentalAgent']['reasoning']}</div>
                        </div>
                        <div class="chat-bubble chat-risk">
                            <div class="chat-header"><span>🛡️ Agent 4: 리스크 총괄 (최종 판단)</span> <span class="score-badge score-badge-risk">포지션: {res['riskManager']['action']} | 비중: {res['riskManager']['positionSize']}</span></div>
                            <div style="font-weight: 600; color: #fca5a5; line-height: 1.6; font-size: 1.05em;">{res['riskManager']['reasoning']}</div>
                        </div>
                    </div>
                    """
                    st.markdown(html_chat, unsafe_allow_html=True)
                except Exception as e: st.error(f"분석 오류: {e}")
    else:
        st.warning("⚠️ 차트 데이터를 불러오지 못했습니다. 1) 상장한 지 200일이 안 된 신규 종목이거나 2) 종목명/코드를 다시 한 번 확인해 주세요.")

# -----------------------------------------------------
# [탭 2] 현금 트래킹 및 AI 리밸런싱
# -----------------------------------------------------
with tab2:
    p_data = st.session_state.p_data
    
    st.markdown(f"<h3 style='color: #f8fafc;'>💼 {st.session_state.user_id}님의 퀀트 포트폴리오</h3>", unsafe_allow_html=True)
    
    with st.expander("💰 자산 및 초기 자본금 세팅", expanded=(p_data['initial_capital'] == 0)):
        new_cap = st.number_input("초기 자본금 (원화 기준, 처음 한 번만 입력)", value=int(p_data['initial_capital']), step=1000000)
        if st.button("자본금 저장"):
            p_data['initial_capital'] = new_cap
            save_portfolio(p_data); st.success("✅ 자본금이 설정되었습니다!"); st.rerun()

    total_invested = sum(r['매수단가'] * r['수량'] for r in p_data['stocks'])
    remaining_cash = p_data['initial_capital'] + p_data['realized_profit'] - total_invested
    
    dis_df = pd.DataFrame(p_data['stocks']) if p_data['stocks'] else pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    
    total_unrealized_profit = 0
    total_asset_value = remaining_cash
    
    if not dis_df.empty:
        prices=[]; profs=[]; rates=[]
        for _, r in dis_df.iterrows():
            _, tck = get_stock_info(r['종목명'])
            p = get_current_price(tck) if tck else 0.0
            prof = (p - r['매수단가']) * r['수량']; rate = (prof / (r['매수단가']*r['수량']) * 100) if r['매수단가']>0 else 0
            prices.append(p); profs.append(prof); rates.append(rate)
            total_unrealized_profit += prof
            total_asset_value += (p * r['수량'])
        dis_df['현재가'] = prices; dis_df['수익금'] = profs; dis_df['수익률(%)'] = rates
        dis_df['평가금액'] = np.array(prices) * dis_df['수량'].astype(float)

    # 💎 [10점 만점 패치] 포트폴리오 요약도 프리미엄 카드로 교체
    html_port_summary = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px;">
        <div class="kpi-card" style="padding: 15px;">
            <div class="kpi-title" style="margin-bottom: 5px;">💵 보유 예수금 (현금)</div>
            <div class="kpi-value-main" style="font-size: 1.4rem;">{int(remaining_cash):,}원</div>
        </div>
        <div class="kpi-card" style="padding: 15px;">
            <div class="kpi-title" style="margin-bottom: 5px;">📦 주식 투자 원금</div>
            <div class="kpi-value-main" style="font-size: 1.4rem;">{int(total_invested):,}원</div>
        </div>
        <div class="kpi-card" style="padding: 15px; border-color: #38bdf8;">
            <div class="kpi-title" style="margin-bottom: 5px;">💎 총 자산 (현금+주식)</div>
            <div class="kpi-value-main" style="font-size: 1.4rem; color: #38bdf8;">{int(total_asset_value):,}원</div>
        </div>
        <div class="kpi-card" style="padding: 15px; border-color: {'#34d399' if total_unrealized_profit > 0 else '#f87171'};">
            <div class="kpi-title" style="margin-bottom: 5px;">📈 현재 평가 손익</div>
            <div class="kpi-value-main" style="font-size: 1.4rem; color: {'#34d399' if total_unrealized_profit > 0 else '#f87171'};">{int(total_unrealized_profit):,}원</div>
        </div>
    </div>
    """
    st.markdown(html_port_summary, unsafe_allow_html=True)

    if not dis_df.empty:
        v1, v2 = st.columns(2)
        with v1:
            fig_p = go.Figure(data=[go.Pie(labels=dis_df['종목명'], values=dis_df['평가금액'], hole=.5, textinfo='percent', textposition='inside', marker=dict(colors=['#38bdf8', '#34d399', '#fbbf24', '#f87171', '#c084fc']))])
            fig_p.update_layout(title_text="포트폴리오 자산 비중", height=280, margin=dict(l=10, r=10, t=40, b=10), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5, font=dict(color="#cbd5e1")), template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_p, use_container_width=True, config={'displayModeBar': False})
        with v2:
            bar_colors = ['#26a69a' if r > 0 else '#ef5350' for r in dis_df['수익률(%)']]
            fig_b = go.Figure(data=[go.Bar(x=dis_df['종목명'], y=dis_df['수익률(%)'], marker_color=bar_colors, text=dis_df['수익률(%)'].apply(lambda x: f"{x:.1f}%"), textposition='outside')])
            fig_b.update_layout(title_text="종목별 수익률 현황", height=280, margin=dict(l=10, r=10, t=40, b=10), xaxis=dict(showticklabels=False), template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_b, use_container_width=True, config={'displayModeBar': False})

    buy_tab, sell_tab = st.tabs(["🛒 종목 매수 (추가)", "💰 종목 매도 (실현손익 기록)"])
    
    with buy_tab:
        with st.form("buy_form"):
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1: p_name = st.text_input("매수 종목명", "현대차")
            with bc2: p_price = st.number_input("매수 단가", min_value=0.0, step=1000.0)
            with bc3: p_qty = st.number_input("매수 수량", min_value=1.0, step=1.0)
            with bc4: 
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                if st.form_submit_button("➕ 포트폴리오 편입", use_container_width=True):
                    an, _ = get_stock_info(p_name)
                    p_data['stocks'].append({'종목명': an if an else p_name, '매수단가': p_price, '수량': p_qty})
                    save_portfolio(p_data); st.rerun()

    with sell_tab:
        if not dis_df.empty:
            with st.form("sell_form"):
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1: s_name = st.selectbox("매도 종목 선택", dis_df['종목명'].tolist())
                with sc2: s_price = st.number_input("실제 매도 단가", min_value=0.0, step=1000.0)
                with sc3: s_qty = st.number_input("매도 수량", min_value=1.0, step=1.0)
                with sc4:
                    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                    if st.form_submit_button("➖ 매도 및 손익 확정", use_container_width=True):
                        idx = next((i for i, item in enumerate(p_data['stocks']) if item["종목명"] == s_name), None)
                        if idx is not None:
                            if s_qty > p_data['stocks'][idx]['수량']: st.error("보유 수량보다 많습니다.")
                            else:
                                realized_pnl = (s_price - p_data['stocks'][idx]['매수단가']) * s_qty
                                p_data['realized_profit'] += realized_pnl
                                p_data['stocks'][idx]['수량'] -= s_qty
                                if p_data['stocks'][idx]['수량'] <= 0: p_data['stocks'].pop(idx)
                                save_portfolio(p_data); st.success(f"매도 완료! 실현손익: {int(realized_pnl):,}원 반영됨"); time.sleep(1); st.rerun()
        else:
            st.info("매도할 보유 종목이 없습니다.")

    if not dis_df.empty:
        st.markdown("<h4 style='color: #f8fafc; margin-top: 20px;'>📋 현재 보유 종목 리스트</h4>", unsafe_allow_html=True)
        # 💎 [10점 만점 패치] 컬럼 포맷팅 적용
        edt_df = st.data_editor(dis_df.drop(columns=['평가금액']), 
            column_config={
                "종목명": st.column_config.TextColumn("종목명", disabled=True), 
                "매수단가": st.column_config.NumberColumn("매수단가 (수정가능)", format="%d ₩"),
                "수량": st.column_config.NumberColumn("수량 (수정가능)"),
                "현재가": st.column_config.NumberColumn("현재가", format="%d ₩", disabled=True), 
                "수익금": st.column_config.NumberColumn("수익금", format="%d ₩", disabled=True), 
                "수익률(%)": st.column_config.NumberColumn("수익률", format="%.2f%%", disabled=True)
            }, hide_index=True, use_container_width=True)
        
        if str(pd.DataFrame(p_data['stocks'])[['매수단가', '수량']].fillna(0).values.tolist()) != str(edt_df[['매수단가', '수량']].fillna(0).values.tolist()):
            p_data['stocks'] = edt_df[['종목명', '매수단가', '수량']].to_dict('records')
            save_portfolio(p_data); st.rerun()
        
        st.markdown("---")
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("✨ 펀드매니저 AI 리밸런싱 (지시서 받기)", use_container_width=True):
                if not gemini_api_key: st.error("API Key를 입력하세요."); st.stop()
                with st.spinner("계좌 자금 흐름과 실시간 거시경제 시황을 통합 분석 중입니다..."):
                    market_news = get_recent_news("글로벌 경제 증시 시황") + get_recent_news("미국 증시 주요 이슈")
                    # 💡 [핵심 버그 수정] 오타(iterrowsiterrows) 수정 완료
                    txt = "\n".join([f"- {r['종목명']} (비중: {(r['현재가']*r['수량'])/total_asset_value*100:.1f}%, 수익률: {r['수익률(%)']:.2f}%)" for _, r in dis_df.iterrows()])
                    rebalance_prompt = f"""
                    당신은 자산운용 펀드매니저입니다. 고객 투자 성향: '{st.session_state.invest_style}'.
                    아래 [오늘의 실시간 시황], [전체 자산 현황]과 [보유 종목 현황]을 분석하여 리밸런싱(비중 조절) 지시서를 JSON 형태로 작성해 주세요.
                    
                    [오늘의 실시간 시황 뉴스]
                    {market_news}

                    [계좌 자산 현황]
                    - 총 자산: {int(total_asset_value):,}원 / 보유 예수금: {int(remaining_cash):,}원
                    - 현재 보유 종목:\n{txt}
                    
                    [분석 수칙]
                    1. '오늘의 실시간 시황 뉴스'를 반드시 반영하여 거시경제 상황에 맞는 액션을 취하세요.
                    2. 현금 비중이 10% 미만이면 위험 상태로 간주, 수익 중인 종목 매도를 통해 현금 확보 지시.
                    3. 출력 형식 (JSON): {{ "market_view": "시황이 반영된 포트폴리오 진단 (2문장)", "action_plan": [ {{ "stock": "종목명", "action": "매수 / 매도 / 유지", "reason": "시황 및 데이터를 근거로 한 이유" }} ], "final_advice": "최종 조언" }}
                    """
                    try:
                        res = get_ai_analysis(rebalance_prompt, gemini_api_key)
                        st.success("✅ AI 리밸런싱 지시서가 도착했습니다.")
                        st.info(f"**📊 포트폴리오 진단:** {res.get('market_view', '')}")
                        st.markdown("#### 🎯 구체적 액션 플랜")
                        for i in res.get("action_plan", []): 
                            if "매수" in i['action']: st.success(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                            elif "매도" in i['action']: st.error(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                            else: st.warning(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                        st.markdown(f"> **💡 펀드매니저 조언:** {res.get('final_advice', '')}")
                    except Exception as e: st.error(f"오류: {e}")
                    
        with btn_c2:
            if st.button("🌅 오늘의 모닝 브리핑 생성", type="primary", use_container_width=True):
                if not gemini_api_key: st.error("API Key를 입력하세요."); st.stop()
                with st.spinner("거시경제 및 시장 동향 분석 중..."):
                    try:
                        market_news = get_recent_news("미국 증시 마감") + get_recent_news("국내 증시 시황")
                        txt = "\n".join([f"- {r['종목명']} 수익률: {r['수익률(%)']:.2f}%" for _, r in dis_df.iterrows()])
                        briefing_prompt = f"글로벌 퀀트 전략가로서 모닝 브리핑을 JSON으로 작성하세요. 성향: {st.session_state.invest_style}\n[시장]\n{market_news}\n[포트폴리오]\n{txt}\n[형식]\n{{\"market_overview\":\"시장요약(3문장)\",\"stock_briefings\":[{{\"stock\":\"명\",\"alert_level\":\"🟢 안전/🟡 주의/🔴 위험\",\"strategy\":\"전략(2문장)\"}}],\"action_plan\":\"성향이 반영된 핵심 지침(1문장)\"}}"
                        res = get_ai_analysis(briefing_prompt, gemini_api_key)
                        
                        st.success("✅ 굿모닝! 오늘의 브리핑이 도착했습니다.")
                        st.markdown("### 🌐 밤사이 시장 동향"); st.info(res.get("market_overview", ""))
                        st.markdown("### 🎯 맞춤 대응 전략")
                        for stock in res.get("stock_briefings", []):
                            lvl = stock.get("alert_level", "")
                            if "안전" in lvl: st.success(f"**{stock['stock']}** ({lvl}) : {stock.get('strategy', '')}")
                            elif "위험" in lvl: st.error(f"**{stock['stock']}** ({lvl}) : {stock.get('strategy', '')}")
                            else: st.warning(f"**{stock['stock']}** ({lvl}) : {stock.get('strategy', '')}")
                        st.markdown(f"> **💡 핵심 지침:** {res.get('action_plan', '')}")
                        
                        if tele_token and tele_chat_id:
                            briefing_msg = f"🌅 <b>모닝 브리핑</b>\n\n🌐 <b>시장 동향</b>\n{res.get('market_overview', '')}\n\n🎯 <b>대응 전략</b>\n"
                            for stock in res.get("stock_briefings", []): briefing_msg += f"- <b>{stock['stock']}</b>: {stock.get('strategy', '')}\n"
                            briefing_msg += f"\n💡 <b>지침({st.session_state.invest_style}):</b> {res.get('action_plan', '')}"
                            send_telegram_message(tele_token, tele_chat_id, briefing_msg)
                            st.toast("📱 텔레그램 전송 완료!")
                    except Exception as e: st.error(f"오류: {e}")

# -----------------------------------------------------
# [탭 3] 매수 급소 프리미엄 스크리너 (Ag-Grid 대안)
# -----------------------------------------------------
with tab3:
    st.markdown("<h3 style='color: #f8fafc;'>📡 매수 급소 AI 스크리너</h3>", unsafe_allow_html=True)
    mode = st.radio("시장 스캔 모드 선택", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"], horizontal=True)
    send_to_telegram = st.checkbox("📱 스캔 완료 시 내 텔레그램으로 전송", value=True)
    
    if st.button("🔎 딥 스캔 실행 (Deep Scan)", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier != 'VIP':
            st.markdown("<div class='paywall-box'><h4>🔒 VIP 전용 기능</h4><p>사이드바에서 로그인 후 이용해 주세요.</p></div>", unsafe_allow_html=True); st.stop()
            
        with st.spinner("시장 전체 종목을 빅데이터 알고리즘으로 필터링 중입니다... (1~2분 소요)"):
            if "한국 우량주" in mode: sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270", "NAVER":"035420", "카카오":"035720"}
            elif "한국 코스피" in mode: sl = get_top_200_stocks()
            else: sl = get_us_top_stocks()
            
            res = []; bar = st.progress(0); txt = st.empty()
            
            for i, (n, c) in enumerate(sl.items()):
                txt.text(f"스캔 진행 중... [{n}] ({i+1}/{len(sl)})")
                try:
                    df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=300)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                    if ind:
                        sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                        is_macd_bullish = ind['MACD_Cross']
                        is_rsi_good = (ind['RSI'] > 50) or (ind['RSI'] <= 35)
                        
                        if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and is_macd_bullish and is_rsi_good:
                            curr_p = float(df['Close'].iloc[-1])
                            ema5 = float(ind['EMA5'])
                            entry2 = float(ind['EMA15'])
                            entry1 = ema5 if curr_p > ema5 else curr_p
                            
                            a = float(ind['ATR'])
                            tar_p = entry1 + (a*4)
                            stop_p = entry1 - (a*2)
                            rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0
                            
                            # 💎 [10점 만점 패치] 스크리너 테이블용 깔끔한 데이터 추출
                            res.append({
                                "종목명": n, 
                                "시그널": "🔥 강력매수" if sc==4 else "👍 분할매수", 
                                "현재가": curr_p, 
                                "1차타점(대기)": entry1,
                                "목표가": tar_p, 
                                "손절가": stop_p, 
                                "손익비(배)": rr_2,
                                "RSI": ind['RSI'],
                                "MACD": "🟢 골든" if is_macd_bullish else "🔴 데드",
                                "볼린저상태": "🚨 스퀴즈" if ind.get("BB_Is_Squeeze") else "확장"
                            })
                except: pass
                bar.progress((i+1)/len(sl))
            txt.text("✅ 빅데이터 스캔 완료!")
            
            if res:
                df_res = pd.DataFrame(res)
                
                # 💎 [10점 만점 패치] 인터랙티브 데이터 그리드 (Ag-Grid 대안 프리미엄 포맷팅)
                st.markdown("<h4 style='color:#34d399; margin-top:20px;'>✨ 필터링 통과 종목 리스트</h4>", unsafe_allow_html=True)
                
                is_us = "미국" in mode
                currency_format = "$ %.2f" if is_us else "₩ %d"
                
                st.dataframe(df_res, 
                    column_config={
                        "종목명": st.column_config.TextColumn("종목명", width="medium"),
                        "시그널": st.column_config.TextColumn("AI 시그널"),
                        "현재가": st.column_config.NumberColumn("현재가", format=currency_format),
                        "1차타점(대기)": st.column_config.NumberColumn("1차 매수(대기)", format=currency_format),
                        "목표가": st.column_config.NumberColumn("목표가", format=currency_format),
                        "손절가": st.column_config.NumberColumn("손절가", format=currency_format),
                        "손익비(배)": st.column_config.NumberColumn("손익비", format="%.1f 배"),
                        "RSI": st.column_config.ProgressColumn("RSI 모멘텀", min_value=0, max_value=100, format="%.1f"),
                        "볼린저상태": st.column_config.TextColumn("볼린저 밴드")
                    }, 
                    hide_index=True, use_container_width=True
                )
                
                st.download_button("📥 CSV 추출", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name="cloud_quant_screener.csv", mime="text/csv")
                
                if send_to_telegram and tele_token and tele_chat_id:
                    chunks = []; msg = f"🚀 <b>프리미엄 퀀트 스캔 완료</b>\n\n총 {len(res)}개 특급 종목 발견\n\n"
                    for r in res:
                        if is_us:
                            curr_p = f"${r['현재가']:,.2f}"; tar_p = f"${r['목표가']:,.2f}"; stop_p = f"${r['손절가']:,.2f}"; entry1_p = f"${r['1차타점(대기)']:,.2f}"
                        else:
                            curr_p = f"{int(r['현재가']):,}원"; tar_p = f"{int(r['목표가']):,}원"; stop_p = f"{int(r['손절가']):,}원"; entry1_p = f"{int(r['1차타점(대기)']):,}원"

                        info = f"<b>{r['종목명']}</b> ({r['시그널']})\n"
                        info += f" └ 📊 <b>RSI:</b> {r['RSI']:.1f} | <b>MACD:</b> {r['MACD']} | <b>BB:</b> {r['볼린저상태']}\n"
                        info += f" └ 🎯 <b>매수대기:</b> {entry1_p} (현재 {curr_p})\n"
                        info += f" └ 🎯 <b>목표:</b> {tar_p} / 🛡️ <b>손절:</b> {stop_p}\n\n"
                        
                        if len(msg) + len(info) > 3800: chunks.append(msg); msg = info
                        else: msg += info
                    chunks.append(msg)
                    for c in chunks: send_telegram_message(tele_token, tele_chat_id, c); time.sleep(0.3)
                    st.success("📱 텔레그램 리포트 전송 완료!")
            else: 
                st.warning("⚠️ 현재 하락장 또는 조정장입니다. 월봉 10선 위 안전한 매수 타점 종목이 없습니다. (현금 보유 권고)")
