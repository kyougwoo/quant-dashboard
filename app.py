import os
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
import time
import re
import textwrap

# 💎 강제 딥 다크 테마 세팅 엔진
theme_config = """[theme]
base='dark'
primaryColor='#38bdf8'
backgroundColor='#0f172a'
secondaryBackgroundColor='#1e293b'
textColor='#f8fafc'
"""
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
write_config = True
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        if f.read() == theme_config:
            write_config = False
if write_config:
    with open(config_path, "w") as f:
        f.write(theme_config)

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

# 💎 최고급 다크 테마 & UI CSS 적용
st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {background-color: transparent !important;}
    @media (max-width: 768px) { .block-container { padding: 2rem 0.5rem !important; } h1 { font-size: 1.5rem !important; } }
    .main-title { font-size: 2.2rem; font-weight: 900; background: -webkit-linear-gradient(45deg, #38bdf8, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px; }
    .title-by { font-size: 0.4em; color: #cbd5e1; font-weight: 600; vertical-align: super; margin-left: 10px; background-color: #1e293b; padding: 4px 10px; border-radius: 12px; border: 1px solid #334155; letter-spacing: 1px; -webkit-text-fill-color: #cbd5e1; }
    .kpi-card { background: linear-gradient(145deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 16px; padding: 20px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); transition: transform 0.2s; height: 100%; }
    .kpi-card:hover { transform: translateY(-5px); border-color: #38bdf8; }
    .kpi-title { font-size: 0.9rem; color: #94a3b8; font-weight: 700; letter-spacing: 1px; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }
    .kpi-value-main { font-size: 1.8rem; font-weight: 900; color: #f8fafc; margin-bottom: 5px; }
    .kpi-value-sub { font-size: 1rem; color: #94a3b8; font-weight: 500; }
    .kpi-highlight { color: #34d399; }
    .kpi-danger { color: #f87171; }
    .chat-container { display: flex; flex-direction: column; gap: 15px; margin-top: 10px; animation: fadeIn 0.8s ease-out forwards; }
    .chat-bubble { padding: 18px 24px; border-radius: 16px; color: #f8fafc; background-color: #1e293b; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 5px solid; position: relative; }
    .chat-macro { border-color: #38bdf8; } .chat-tech { border-color: #34d399; } .chat-funda { border-color: #fbbf24; } .chat-risk { border-color: #ef4444; background: linear-gradient(to right, #451a1a, #1e293b); }
    .chat-header { font-weight: 800; margin-bottom: 12px; font-size: 1.1em; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }
    .score-badge { background: #0f172a; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; color: #38bdf8; border: 1px solid #1e293b; }
    .score-badge-risk { background: #7f1d1d; color: #fca5a5; border-color: #991b1b; font-size: 1em; padding: 6px 14px;}
    @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
    .stButton > button { border-radius: 12px !important; font-weight: 800 !important; transition: all 0.3s; background-color: #1e293b !important; color: #f8fafc !important; border: 1px solid #38bdf8 !important; }
    .stButton > button:hover { background-color: #38bdf8 !important; color: #0f172a !important; border-color: #38bdf8 !important; }
</style>
""", unsafe_allow_html=True)

def init_db():
    if not FIREBASE_AVAILABLE: return None, f"🚨 라이브러리 누락: {FIREBASE_IMPORT_ERROR}"
    try:
        raw_s = str(st.secrets.get("FIREBASE_JSON", st.secrets.get("firebase", "")))
        if not raw_s: return None, "❌ 설정창(Secrets) 비어있음."
        try:
            creds_dict = json.loads(raw_s, strict=False)
            if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds, project=creds_dict.get("project_id")), "✅ 연결 성공"
        except:
            pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', raw_s)
            em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', raw_s)
            pk_raw = raw_s[raw_s.find("-----BEGIN PRIVATE KEY-----") : raw_s.find("-----END PRIVATE KEY-----") + 25]
            pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
            private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
            creds = service_account.Credentials.from_service_account_info({"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": "https://oauth2.googleapis.com/token"})
            return firestore.Client(credentials=creds, project=pm.group(1)), "✅ 연결 성공"
    except Exception as e: return None, f"❌ 접속 거부: {e}"

if 'db_client' not in st.session_state: st.session_state.db_client, st.session_state.db_msg = init_db()
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
                            target_tier = 'Admin' if login_id.lower() == 'admin' else 'VIP' if login_id.lower() == 'vip' else 'Free'
                            if user_doc.exists and user_doc.to_dict().get('password') == login_pw:
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, user_doc.to_dict().get('tier', 'Free')
                            elif not user_doc.exists:
                                user_ref.set({'password': login_pw, 'tier': target_tier, 'created_at': datetime.now()})
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, target_tier
                            st.rerun()
                        except: st.error("DB 오류")
                    else:
                        st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, 'Admin'; st.rerun()
        else:
            st.success(f"환영합니다, **{st.session_state.user_id}**님! (등급: {st.session_state.user_tier})")
            if st.button("로그아웃", use_container_width=True): st.session_state.logged_in = False; st.rerun()
                
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
            if input_chat_id != tele_chat_id and st.button("알림 ID 저장"): user_ref.update({'telegram_chat_id': input_chat_id}); st.rerun()

st.markdown("---")

def load_portfolio():
    default_data = {'initial_capital': 0, 'realized_profit': 0, 'stocks': []}
    if db:
        try:
            doc = db.collection('portfolios').document(st.session_state.user_id).get()
            if doc.exists: return doc.to_dict()
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
    with open(f'portfolio_data_{st.session_state.user_id}.json', 'w') as f: json.dump(data, f)

if 'p_data' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.p_data, st.session_state.current_user = load_portfolio(), st.session_state.user_id

@st.cache_data(ttl=86400, show_spinner=False)
def load_krx_data():
    try:
        df = fdr.StockListing('KRX-DESC')
        if not df.empty: return df
    except: pass
    try: return pd.concat([fdr.StockListing('KOSPI'), fdr.StockListing('KOSDAQ')], ignore_index=True)
    except: raise ValueError("데이터 로드 실패")

def get_stock_info(query):
    query = str(query).strip().upper()
    if not query: return None, None
    fallback = { "삼성전자":"005930", "SK하이닉스":"000660", "카카오":"035720", "현대차":"005380", "기아":"000270", "알테오젠":"196170", "NAVER":"035420", "LG에너지솔루션":"373220", "에코프로비엠":"247540", "HLB":"028300", "아난티":"025980", "LG전자":"066570", "영풍":"000670"}
    if query in fallback: return query, fallback[query]
    
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=3)
        items = res.json().get('items', [[]])[0]
        if items:
            for item in items:
                if item[0].replace(" ", "").upper() == query.replace(" ", "").upper() and str(item[1]).isdigit() and len(str(item[1])) == 6:
                    return item[0], str(item[1])
            for item in items:
                if str(item[1]).isdigit() and len(str(item[1])) == 6: return item[0], str(item[1])
    except: pass
        
    try:
        df_krx = load_krx_data()
        if df_krx is not None and not df_krx.empty:
            col_map = {c: 'Code' for c in df_krx.columns if str(c).upper() in ['SYMBOL', 'CODE', '종목코드', '단축코드']}
            col_map.update({c: 'Name' for c in df_krx.columns if str(c).upper() in ['NAME', '종목명', '회사명']})
            df_krx = df_krx.rename(columns=col_map)
            df_krx['Name_NoSpace'] = df_krx['Name'].astype(str).str.replace(" ", "").str.upper()
            if query.isdigit() and len(query) == 6:
                match = df_krx[df_krx['Code'].astype(str).str.zfill(6) == query]
                if not match.empty: return match['Name'].values[0], query
            match = df_krx[df_krx['Name_NoSpace'] == query.replace(" ", "")]
            if not match.empty: return match['Name'].values[0], str(match['Code'].values[0]).replace('.0', '').zfill(6)
            match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query.replace(" ", ""), na=False, regex=False)]
            if not match_partial.empty: 
                best = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]
                return best['Name'], str(best['Code']).replace('.0', '').zfill(6)
    except: pass
    return query, query if query.isdigit() else None

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
def get_kosdaq_top_200_stocks():
    try:
        df = fdr.StockListing('KOSDAQ')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except: return {"에코프로비엠":"247540", "알테오젠":"196170", "HLB":"028300"}

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

@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    for attempt in range(5):
        try:
            res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            return json.loads(res.text.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            if attempt < 4: time.sleep(2); continue
            raise e

def calculate_cloud_indicators(df):
    if df is None or df.empty: return None, {}
    df = df[~df.index.duplicated(keep='first')].dropna(subset=['Close'])
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
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal'] 
    
    recent_60 = df.tail(60)
    df['Vol_Ref_Price'] = float(df['Close'].iloc[-1]) if recent_60['Volume'].sum() == 0 else float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
    
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']), 
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8),
        "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
        "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']), "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']), "최대 거래량 종가 돌파": bool(latest['Close'] > latest['Vol_Ref_Price'])}
    }
    return df, indicators

# 💡 백테스트 및 매수/매도 마커 엔진
def run_backtest_with_markers(df):
    trades = []; position = 0; entry_price = 0; entry_atr = 0; balance = 10000000 
    buy_dates=[]; buy_prices=[]; sell_dates=[]; sell_prices=[]
    
    if df is None or df.empty: 
        return {'total_trades': 0, 'win_rate': 0, 'total_return': 0}, {'x': buy_dates, 'y': buy_prices}, {'x': sell_dates, 'y': sell_prices}
        
    for i in range(1, len(df)):
        prev, curr, date = df.iloc[i-1], df.iloc[i], df.index[i]
        if pd.isna(curr.get('EMA200', np.nan)): continue
        if position == 0:
            if prev['EMA5'] <= prev['EMA15'] and curr['EMA5'] > curr['EMA15'] and curr['Close'] > curr['EMA200']:
                position = 1; entry_price = curr['Close']; entry_atr = curr['ATR'] if not pd.isna(curr.get('ATR', np.nan)) and curr['ATR']>0 else curr['Close']*0.05
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
    wins = [t for t in sells if t.get('profit_pct', 0) > 0]
    stats = {'total_trades': len(sells), 'win_rate': (len(wins)/len(sells)*100) if sells else 0, 'total_return': ((balance-10000000)/10000000)*100}
    return stats, {'x': buy_dates, 'y': buy_prices}, {'x': sell_dates, 'y': sell_prices}

def format_price(price, ticker): return f"{int(price):,}원" if str(ticker).isdigit() else f"${price:,.2f}"

def send_telegram_message(token, chat_id, text):
    try: return requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5).status_code == 200
    except: return False

@st.cache_data(ttl=3600)
def get_current_price(ticker):
    try:
        df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        return float(df['Close'].iloc[-1]) if not df.empty else 0.0
    except: return 0.0

col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "영풍", "애플(AAPL)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (영문 코드 가능)", "삼성전자")
    else: stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search; st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
is_admin = (st.session_state.user_tier == 'Admin')
tab_titles = ["📊 프로 차트 분석", "💼 포트폴리오 관리", "📡 프리미엄 스크리너"]
if is_admin: tab_titles.append("🛠️ 회원 관리 (Admin)")
tabs = st.tabs(tab_titles)
tab1, tab2, tab3 = tabs[0], tabs[1], tabs[2]
if is_admin: tab4 = tabs[3]

# -----------------------------------------------------
# [탭 1] 프로 차트 분석
# -----------------------------------------------------
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("❌ 종목을 찾을 수 없습니다."); st.stop()

    st.markdown(f"<h3 style='color: #f8fafc;'>📊 {actual_name} <span style='font-size: 0.6em; color: #64748b;'>{ticker}</span></h3>", unsafe_allow_html=True)
    with st.spinner("터미널 데이터 동기화 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) 
        except: 
            df = None; tech_ind = {}; stats = {'total_trades': 0, 'win_rate': 0, 'total_return': 0}
            buy_m = {'x': [], 'y': []}; sell_m = {'x': [], 'y': []}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) 
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Upper'], mode='lines', line=dict(color='rgba(56, 189, 248, 0.5)', width=1), name='BB 상단'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Lower'], mode='lines', line=dict(color='rgba(56, 189, 248, 0.5)', width=1), fill='tonexty', fillcolor='rgba(56, 189, 248, 0.05)', name='BB 하단'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#06b6d4', width=1.5), name='5일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='#ef4444', width=2, dash='dash'), name='최대 매물대'), row=1, col=1)
        
        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]
        b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]
        s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', size=14, color='#34d399', line=dict(width=1, color='#1e293b')), name='시스템 매수'), row=1, col=1)
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', size=14, color='#f87171', line=dict(width=1, color='#1e293b')), name='시스템 매도'), row=1, col=1)

        colors = ['#26a69a' if row['Close'] >= row['Open'] else '#ef5350' for _, row in display_df.iterrows()]
        fig.add_trace(go.Bar(x=display_df.index, y=display_df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

        curr_p = float(df['Close'].iloc[-1])
        fig.add_hline(y=curr_p, line_dash="dot", line_color="#38bdf8", line_width=1.5, annotation_text=f"현재가: {format_price(curr_p, ticker)}", annotation_position="right", annotation_font=dict(color="white"), annotation_bgcolor="#0284c7", row=1, col=1)

        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False, height=550, margin=dict(l=10, r=60, t=10, b=20), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown(f"""
        <div style='background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155;'>
            <h4 style='color: #f8fafc; margin-top: 0; margin-bottom: 10px; font-size: 1rem;'>📊 시스템 백테스트 요약 (최근 2년)</h4>
            <div style='display: flex; gap: 20px;'>
                <div><span style='color: #94a3b8; font-size: 0.9em;'>누적 수익률:</span> <span style='color: {"#34d399" if stats["total_return"] > 0 else "#f87171"}; font-weight: bold;'>{stats['total_return']:.1f}%</span></div>
                <div><span style='color: #94a3b8; font-size: 0.9em;'>승률:</span> <span style='color: #38bdf8; font-weight: bold;'>{stats['win_rate']:.1f}%</span></div>
                <div><span style='color: #94a3b8; font-size: 0.9em;'>총 매매 횟수:</span> <span style='color: #f8fafc; font-weight: bold;'>{stats['total_trades']}회</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        ema5 = float(tech_ind['EMA5'])
        entry2 = float(tech_ind['EMA15'])
        entry1 = ema5 if curr_p > ema5 else curr_p
        tar_p = entry1 + (float(tech_ind['ATR']) * 4)
        stop_p = entry1 - (float(tech_ind['ATR']) * 2)
        trailing_stop = curr_p - (float(tech_ind['ATR']) * 2.5)

        html_kpi = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px;">
            <div class="kpi-card">
                <div class="kpi-title">🎯 스마트 대기 타점 (눌림목)</div>
                <div class="kpi-value-main kpi-highlight">1차: {format_price(entry1, ticker)}</div>
                <div class="kpi-value-sub">2차: {format_price(entry2, ticker)} (15일선 지지)</div>
            </div>
            <div class="kpi-card" style="border-color: #f87171;">
                <div class="kpi-title">🛡️ 목표 & 수익 보존 라인</div>
                <div class="kpi-value-main" style="color: #60a5fa;">목표가: {format_price(tar_p, ticker)}</div>
                <div class="kpi-value-sub text-red-400 font-bold" style="color:#f87171; font-weight:900;">✨트레일링스탑: {format_price(trailing_stop, ticker)}</div>
            </div>
        </div>
        """
        st.markdown(html_kpi, unsafe_allow_html=True)

        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>☁️ 클라우드 4원칙 체크</h4>", unsafe_allow_html=True)
            if tech_ind:
                for rule, passed in tech_ind["Cloud_Rules"].items(): 
                    color = "#34d399" if passed else "#64748b"
                    st.markdown(f"<span style='color: {color}; font-weight: 500;'>{'✅' if passed else '❌'} {rule}</span>", unsafe_allow_html=True)
                
                rsi_val = tech_ind.get('RSI', 50)
                rsi_color = "#f87171" if rsi_val >= 70 else "#38bdf8" if rsi_val <= 30 else "#cbd5e1"
                macd_state = "🚀 MACD 선취매 턴어라운드 포착!" if tech_ind.get('MACD_Early_Entry') else ("🟢 정통 골든크로스(매수)" if tech_ind.get('MACD_Cross') else "🔴 데드크로스(매도)")
                rsi_state = "📉 RSI 과매도 바닥 턴어라운드 포착!" if tech_ind.get('RSI_Turnaround') else f"{rsi_val:.1f}"
                bb_sig = "📉 스퀴즈 (응축 폭발전야!)" if tech_ind.get('BB_Is_Squeeze') else "📈 일반 확장"
                
                st.markdown(f"""
                <div style='background: #1e293b; padding: 15px; border-radius: 12px; margin-top: 15px; border-left: 4px solid #3b82f6;'>
                    <div style='margin-bottom: 8px;'><b>RSI (14):</b> <span style='color: {rsi_color}; font-weight: bold;'>{rsi_state}</span></div>
                    <div style='margin-bottom: 8px;'><b>MACD:</b> {macd_state}</div>
                    <div><b>볼린저밴드:</b> <span style='color: #fbbf24;'>{bb_sig}</span></div>
                </div>
                """, unsafe_allow_html=True)
                
                if tech_ind.get('Is_Above_Monthly_EMA10'): st.markdown(f"<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(52, 211, 153, 0.1); color: #34d399; font-weight: 600;'>🟢 월봉 10선 생명선 위 (안전구간)</div>", unsafe_allow_html=True)
                else: st.markdown(f"<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(248, 113, 113, 0.1); color: #f87171; font-weight: 600;'>🔴 월봉 10선 생명선 이탈 (위험구간)</div>", unsafe_allow_html=True)
            
        with info_col2:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>📰 실시간 마켓 내러티브</h4>", unsafe_allow_html=True)
            news_list = get_recent_news(actual_name)[:4]
            news_html = "<div style='display: flex; flex-direction: column; gap: 8px;'>"
            for news in news_list: news_html += f"<div style='background: #1e293b; padding: 10px; border-radius: 8px; font-size: 0.85em; color: #cbd5e1; border-left: 3px solid #64748b;'>{news}</div>"
            st.markdown(news_html + "</div>", unsafe_allow_html=True)
            
            if st.button("📰 AI 뉴스 감성(Sentiment) 스코어 분석", use_container_width=True):
                if not gemini_api_key: st.error("위쪽 시스템 설정에서 API Key를 입력하세요!"); st.stop()
                with st.spinner("AI가 최신 뉴스를 꼼꼼히 읽고 있습니다..."):
                    try:
                        sentiment_res = get_ai_analysis(f"다음 뉴스들의 전반적인 투자 감성을 0~100점으로 평가해줘. 형식(JSON): {{\"score\": 정수, \"verdict\": \"강력 매수/긍정적/중립/부정적/강력 매도\", \"summary\": \"3줄 요약\"}} 뉴스: {news_list}", gemini_api_key)
                        score = sentiment_res.get('score', 50)
                        bar_color = "#34d399" if score >= 60 else "#f87171" if score <= 40 else "#fbbf24"
                        st.markdown(f"""
                        <div style='background: #0f172a; border: 1px solid {bar_color}; padding: 15px; border-radius: 12px; margin-top: 15px;'>
                            <h4 style='margin-top:0; color:{bar_color};'>🔥 AI 감성 스코어: {score}점 ({sentiment_res.get('verdict', '중립')})</h4>
                            <div style='width: 100%; background-color: #334155; border-radius: 10px; height: 10px; margin-bottom: 10px;'><div style='width: {score}%; background-color: {bar_color}; height: 10px; border-radius: 10px;'></div></div>
                            <p style='font-size:0.9em; color:#cbd5e1;'>{sentiment_res.get('summary', '')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e: st.error(f"분석 실패: {e}")

        st.markdown("<h3 style='color: #38bdf8; margin-top:30px;'>🤖 Harness 4-Agent 분석 엔진</h3>", unsafe_allow_html=True)
        if st.button("🚀 4-Agent 회의 소집 (분석 실행)", type="primary", use_container_width=True):
            if not gemini_api_key: st.error("API Key를 입력하세요!"); st.stop()
            with st.spinner("4명의 AI 전문가가 차트와 뉴스를 분석하며 토론 중입니다..."):
                try:
                    res = get_ai_analysis(f"종목: {actual_name}, 뉴스: {news_list}, 월봉10선: {'안전' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험'}, 성향: {st.session_state.invest_style}. 출력 형식(JSON): {{\"macroAgent\": {{\"score\": 80, \"reasoning\": \"...\"}}, \"technicalAgent\": {{\"score\": 70, \"reasoning\": \"...\"}}, \"fundamentalAgent\": {{\"score\": 60, \"reasoning\": \"...\"}}, \"riskManager\": {{\"action\": \"매수/관망/매도\", \"positionSize\": \"20%\", \"reasoning\": \"...\"}}}}", gemini_api_key)
                    html_chat = f"""
                    <div class="chat-container">
                        <div class="chat-bubble chat-macro"><div class="chat-header"><span>🌍 Agent 1: 거시경제 전략가</span> <span class="score-badge">Score: {res['macroAgent']['score']}/100</span></div><div style="line-height: 1.6;">{res['macroAgent']['reasoning']}</div></div>
                        <div class="chat-bubble chat-tech"><div class="chat-header"><span>📈 Agent 2: 기술적 분석가</span> <span class="score-badge">Score: {res['technicalAgent']['score']}/100</span></div><div style="line-height: 1.6;">{res['technicalAgent']['reasoning']}</div></div>
                        <div class="chat-bubble chat-funda"><div class="chat-header"><span>📰 Agent 3: 펀더멘털 매니저</span> <span class="score-badge">Score: {res['fundamentalAgent']['score']}/100</span></div><div style="line-height: 1.6;">{res['fundamentalAgent']['reasoning']}</div></div>
                        <div class="chat-bubble chat-risk"><div class="chat-header"><span>🛡️ Agent 4: 리스크 총괄 (최종 판단)</span> <span class="score-badge score-badge-risk">포지션: {res['riskManager']['action']} | 비중: {res['riskManager']['positionSize']}</span></div><div style="font-weight: 600; color: #fca5a5; line-height: 1.6;">{res['riskManager']['reasoning']}</div></div>
                    </div>
                    """
                    st.markdown(html_chat, unsafe_allow_html=True)
                except Exception as e: st.error(f"분석 오류: {e}")

# -----------------------------------------------------
# [탭 2] 포트폴리오 관리
# -----------------------------------------------------
with tab2:
    p_data = st.session_state.p_data
    st.markdown(f"<h3 style='color: #f8fafc;'>💼 {st.session_state.user_id}님의 퀀트 포트폴리오</h3>", unsafe_allow_html=True)
    
    with st.expander("💰 초기 자본금 세팅", expanded=(p_data['initial_capital'] == 0)):
        new_cap = st.number_input("초기 자본금 (원화)", value=int(p_data['initial_capital']), step=1000000)
        if st.button("저장"): p_data['initial_capital'] = new_cap; save_portfolio(p_data); st.rerun()

    total_invested = sum(r['매수단가'] * r['수량'] for r in p_data['stocks'])
    remaining_cash = p_data['initial_capital'] + p_data['realized_profit'] - total_invested
    dis_df = pd.DataFrame(p_data['stocks']) if p_data['stocks'] else pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    
    total_unrealized_profit = 0
    total_asset_value = remaining_cash
    
    if not dis_df.empty:
        prices=[]; profs=[]; rates=[]; trailing_stops=[]
        for _, r in dis_df.iterrows():
            _, tck = get_stock_info(r['종목명'])
            p = get_current_price(tck) if tck else 0.0
            prof = (p - r['매수단가']) * r['수량']
            rate = (prof / (r['매수단가']*r['수량']) * 100) if r['매수단가']>0 else 0
            
            try:
                temp_df = fdr.DataReader(tck, (datetime.today()-timedelta(days=100)).strftime('%Y-%m-%d'))
                tr = pd.concat([temp_df['High']-temp_df['Low'], (temp_df['High']-temp_df['Close'].shift(1)).abs(), (temp_df['Low']-temp_df['Close'].shift(1)).abs()], axis=1).max(axis=1)
                atr = tr.rolling(14).mean().iloc[-1]
                t_stop = p - (atr * 2.5) if rate > 0 else r['매수단가'] - (atr * 2)
            except:
                t_stop = p * 0.95
                
            prices.append(p); profs.append(prof); rates.append(rate); trailing_stops.append(t_stop)
            total_unrealized_profit += prof
            total_asset_value += (p * r['수량'])
            
        dis_df['현재가'] = prices; dis_df['수익금'] = profs; dis_df['수익률(%)'] = rates
        dis_df['🛡️손절/익절가'] = trailing_stops 
        dis_df['평가금액'] = np.array(prices) * dis_df['수량'].astype(float)

    st.markdown(f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
        <div class="kpi-card" style="padding: 15px;"><div class="kpi-title">💵 보유 현금</div><div class="kpi-value-main" style="font-size: 1.4rem;">{int(remaining_cash):,}원</div></div>
        <div class="kpi-card" style="padding: 15px;"><div class="kpi-title">📦 투자 원금</div><div class="kpi-value-main" style="font-size: 1.4rem;">{int(total_invested):,}원</div></div>
        <div class="kpi-card" style="padding: 15px; border-color: #38bdf8;"><div class="kpi-title">💎 총 자산</div><div class="kpi-value-main" style="font-size: 1.4rem; color: #38bdf8;">{int(total_asset_value):,}원</div></div>
        <div class="kpi-card" style="padding: 15px; border-color: {'#34d399' if total_unrealized_profit > 0 else '#f87171'};"><div class="kpi-title">📈 평가 손익</div><div class="kpi-value-main" style="font-size: 1.4rem; color: {'#34d399' if total_unrealized_profit > 0 else '#f87171'};">{int(total_unrealized_profit):,}원</div></div>
    </div>
    """, unsafe_allow_html=True)

    buy_tab, sell_tab, del_tab = st.tabs(["🛒 매수", "💰 매도", "🗑️ 오류 삭제"])
    with buy_tab:
        with st.form("buy"):
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1: p_n = st.text_input("종목명")
            with bc2: p_p = st.number_input("매수단가", min_value=0.0)
            with bc3: p_q = st.number_input("수량", min_value=1.0)
            with bc4: st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True); submit = st.form_submit_button("추가", use_container_width=True)
            if submit: an, _ = get_stock_info(p_n); p_data['stocks'].append({'종목명': an if an else p_n, '매수단가': p_p, '수량': p_q}); save_portfolio(p_data); st.rerun()
    with sell_tab:
        if not dis_df.empty:
            with st.form("sell"):
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1: s_n = st.selectbox("종목 선택", dis_df['종목명'].tolist())
                with sc2: s_p = st.number_input("매도단가", min_value=0.0)
                with sc3: s_q = st.number_input("수량", min_value=1.0)
                with sc4: st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True); submit2 = st.form_submit_button("매도 확정", use_container_width=True)
                if submit2:
                    idx = next((i for i, v in enumerate(p_data['stocks']) if v["종목명"] == s_n), None)
                    if idx is not None and s_q <= p_data['stocks'][idx]['수량']:
                        p_data['realized_profit'] += (s_p - p_data['stocks'][idx]['매수단가']) * s_q
                        p_data['stocks'][idx]['수량'] -= s_q
                        if p_data['stocks'][idx]['수량'] <= 0: p_data['stocks'].pop(idx)
                        save_portfolio(p_data); st.rerun()
    with del_tab:
        if not dis_df.empty:
            with st.form("del"):
                dc1, dc2 = st.columns([3,1])
                with dc1: d_n = st.selectbox("기록 삭제", dis_df['종목명'].tolist())
                with dc2: st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True); submit3 = st.form_submit_button("영구 삭제", use_container_width=True)
                if submit3:
                    idx = next((i for i, v in enumerate(p_data['stocks']) if v["종목명"] == d_n), None)
                    if idx is not None: p_data['stocks'].pop(idx); save_portfolio(p_data); st.rerun()

    if not dis_df.empty:
        st.markdown("<h4 style='color: #f8fafc; margin-top: 20px;'>📋 보유 종목 (스마트 트레일링 적용)</h4>", unsafe_allow_html=True)
        # 💡 [프론트엔드 에러 픽스] format 파라미터 내 특수기호(₩, %) 제거 및 컬럼명으로 이동하여 렌더링 충돌 완벽 방어
        edt_df = st.data_editor(dis_df.drop(columns=['평가금액']), 
            column_config={
                "현재가": st.column_config.NumberColumn("현재가(원)", format="%d", disabled=True), 
                "수익금": st.column_config.NumberColumn("수익금(원)", format="%d", disabled=True), 
                "수익률(%)": st.column_config.NumberColumn("수익률(%)", format="%.2f", disabled=True),
                "🛡️손절/익절가": st.column_config.NumberColumn("손절/익절가(원)", format="%d", disabled=True)
            }, hide_index=True, use_container_width=True
        )
        
        if str(pd.DataFrame(p_data['stocks'])[['매수단가', '수량']].fillna(0).values.tolist()) != str(edt_df[['매수단가', '수량']].fillna(0).values.tolist()):
            p_data['stocks'] = edt_df[['종목명', '매수단가', '수량']].to_dict('records')
            save_portfolio(p_data); st.rerun()

# -----------------------------------------------------
# [탭 3] VIP 스크리너 (UI 에러 방지, 텔레그램 포맷 100% 복구)
# -----------------------------------------------------
with tab3:
    st.markdown("<h3 style='color: #f8fafc;'>📡 매수 급소 AI 스크리너</h3>", unsafe_allow_html=True)
    mode = st.radio("시장 스캔 모드 선택", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🚀 한국 코스닥 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"], horizontal=True)
    send_to_telegram = st.checkbox("📱 스캔 완료 시 내 텔레그램으로 전송", value=True)
    
    if st.button("🔎 딥 스캔 실행", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier not in ['VIP', 'Admin']:
            st.markdown("<div class='paywall-box'><h4>🔒 VIP 전용 기능</h4></div>", unsafe_allow_html=True); st.stop()
            
        with st.spinner("빅데이터 필터링 중..."):
            if "우량주" in mode: sl = {"삼성전자":"005930", "SK하이닉스":"000660", "카카오":"035720", "현대차":"005380", "NAVER":"035420", "기아":"000270", "셀트리온":"068270", "KB금융":"105560", "POSCO홀딩스":"005490", "LG화학":"051910"}
            elif "코스피" in mode: sl = get_top_200_stocks()
            elif "코스닥" in mode: sl = get_kosdaq_top_200_stocks()
            else: sl = get_us_top_stocks()
            
            res = []; bar = st.progress(0); txt = st.empty()
            # 과거 700일 데이터 로드
            for i, (n, c) in enumerate(sl.items()):
                txt.text(f"스캔 중... [{n}]")
                try:
                    df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                    if ind:
                        sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                        is_smart = ind['MACD_Early_Entry'] or ind['RSI_Turnaround'] or ind['MACD_Cross']
                        
                        if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                            curr_p = float(df['Close'].iloc[-1])
                            ema5 = float(ind['EMA5'])
                            entry2 = float(ind['EMA15'])
                            entry1 = ema5 if curr_p > ema5 else curr_p
                            a = float(ind['ATR'])
                            tar_p = entry1 + (a*4)
                            stop_p = entry1 - (a*2)
                            rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0.0
                            
                            tags = []
                            if ind['MACD_Early_Entry']: tags.append("🚀선취매")
                            if ind['RSI_Turnaround']: tags.append("📉RSI턴")
                            if ind['MACD_Cross']: tags.append("🟢골든크로스")
                            
                            res.append({
                                "종목명": str(n), 
                                "시그널": "🔥 강력매수" if is_smart else "👍 분할매수",
                                "포착원인": " + ".join(tags) if tags else "추세추종",
                                "현재가": float(curr_p), 
                                "1차타점(대기)": float(entry1),
                                "목표가": float(tar_p), 
                                "손절가": float(stop_p), 
                                "손익비(배)": float(rr_2),
                                "RSI": float(ind.get('RSI', 50)),
                                "MACD": "🟢 상승" if ind.get("MACD_Cross", False) else "🔴 하락",
                                "볼린저상태": "🚨 스퀴즈" if ind.get("BB_Is_Squeeze") else "확장"
                            })
                except: pass
                bar.progress((i+1)/len(sl))
            txt.text("✅ 스캔 완료!")
            
            if res:
                df_res = pd.DataFrame(res)
                
                # 💡 [프론트엔드 에러 원천 차단] 무한대, 결측치 치환 및 숫자형 데이터 강제 변환
                df_res = df_res.replace([np.inf, -np.inf], 0).fillna(0)
                for col in ["현재가", "1차타점(대기)", "목표가", "손절가", "손익비(배)", "RSI"]:
                    df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
                
                st.markdown("<h4 style='color:#34d399; margin-top:20px;'>✨ 필터링 통과 종목 리스트</h4>", unsafe_allow_html=True)
                
                # 💡 [화면 깨짐 완벽 방지] format 파라미터에 ₩, $ 등 특수기호 삽입 시 화면이 깨지는 현상 수정 (단위는 컬럼명으로 이동)
                is_us = "미국" in mode
                currency_format = "%.2f" if is_us else "%d"
                col_suffix = "(달러)" if is_us else "(원)"
                
                st.dataframe(df_res, 
                    column_config={
                        "종목명": st.column_config.TextColumn("종목명", width="medium"),
                        "시그널": st.column_config.TextColumn("AI 시그널"),
                        "포착원인": st.column_config.TextColumn("🔥포착원인", width="large"),
                        "현재가": st.column_config.NumberColumn(f"현재가{col_suffix}", format=currency_format),
                        "1차타점(대기)": st.column_config.NumberColumn(f"1차 매수{col_suffix}", format=currency_format),
                        "목표가": st.column_config.NumberColumn(f"목표가{col_suffix}", format=currency_format),
                        "손절가": st.column_config.NumberColumn(f"손절가{col_suffix}", format=currency_format),
                        "손익비(배)": st.column_config.NumberColumn("손익비", format="%.1f"),
                        "RSI": st.column_config.ProgressColumn("RSI 모멘텀", min_value=0, max_value=100, format="%.1f"),
                        "MACD": st.column_config.TextColumn("MACD 추세"),
                        "볼린저상태": st.column_config.TextColumn("볼린저 밴드")
                    }, 
                    hide_index=True, use_container_width=True
                )
                
                st.download_button("📥 CSV 추출", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name="cloud_quant_screener.csv", mime="text/csv")
                
                # 텔레그램 분할 전송 로직 (정상 작동 확인)
                if send_to_telegram and tele_token and tele_chat_id:
                    chunks = []
                    msg = f"🚀 <b>프리미엄 퀀트 스캔 완료</b>\n\n총 {len(res)}개 특급 종목 발견\n\n"
                    for r in res:
                        cp = f"${r['현재가']:,.2f}" if is_us else f"{int(r['현재가']):,}원"
                        ep = f"${r['1차타점(대기)']:,.2f}" if is_us else f"{int(r['1차타점(대기)']):,}원"
                        tp = f"${r['목표가']:,.2f}" if is_us else f"{int(r['목표가']):,}원"
                        sp = f"${r['손절가']:,.2f}" if is_us else f"{int(r['손절가']):,}원"
                        
                        info = f"<b>{r['종목명']}</b> ({r['시그널']})\n"
                        info += f" └ ✨ <b>포착원인:</b> {r['포착원인']}\n"
                        info += f" └ 📊 <b>RSI:</b> {r['RSI']:.1f} | <b>BB:</b> {r['볼린저상태']}\n"
                        info += f" └ 🎯 <b>매수대기:</b> {ep} (현재 {cp})\n"
                        info += f" └ 🎯 <b>목표:</b> {tp} / 🛡️ <b>손절:</b> {sp}\n\n"
                        
                        if len(msg) + len(info) > 3800: 
                            chunks.append(msg)
                            msg = info
                        else: 
                            msg += info
                    chunks.append(msg)
                    
                    for c in chunks: 
                        send_telegram_message(tele_token, tele_chat_id, c)
                        time.sleep(0.3)
                    st.success("📱 텔레그램 전송 완료!")
            else: st.warning("월봉 10선 위 안전한 타점이 없습니다.")

# -----------------------------------------------------
# [탭 4] Admin (기존 유저 DB 관리)
# -----------------------------------------------------
if is_admin:
    with tab4:
        st.markdown("<h3 style='color: #f8fafc;'>🛠️ 최고 관리자 시스템</h3>", unsafe_allow_html=True)
        if db:
            users_stream = db.collection('users').stream()
            user_list = [{"아이디": u.id, "등급": u.to_dict().get("tier", "Free"), "가입일": str(u.to_dict().get("created_at", ""))} for u in users_stream]
            if user_list:
                df_users = pd.DataFrame(user_list)
                st.data_editor(df_users, hide_index=True, use_container_width=True)
        else: st.error("Firebase 미연결")
