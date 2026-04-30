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

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background-color: transparent !important;}
    @media (max-width: 768px) {
        .block-container { padding: 3rem 0.5rem 2rem 0.5rem !important; }
        h1 { font-size: 1.4rem !important; margin-bottom: 10px !important; line-height: 1.3 !important; }
        .stButton>button { width: 100% !important; padding: 0.8rem !important; font-size: 1.1rem !important; font-weight: 700 !important; border-radius: 10px !important; }
    }
    .paywall-box { padding: 15px; background-color: #fff3cd; border-left: 5px solid #ffc107; border-radius: 5px; margin-bottom: 15px; color: #856404; }
    .title-by { font-size: 0.55em; color: #4b5563; font-weight: 600; vertical-align: middle; margin-left: 8px; background-color: #f3f4f6; padding: 3px 8px; border-radius: 12px; border: 1px solid #e5e7eb; display: inline-block; position: relative; top: -3px; }
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
st.markdown("<h1>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("**(클라우드 타점 분석 + 자동 예수금 트래킹 + AI 리밸런싱)**")

with st.expander("👤 내 계정 및 시스템 설정", expanded=not st.session_state.logged_in):
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
        st.markdown("### ⚙️ 설정")
        st.session_state.invest_style = st.selectbox("🎯 나의 투자 성향", ["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"], index=["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"].index(st.session_state.invest_style))
        gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if not gemini_api_key: gemini_api_key = st.text_input("Gemini API Key", type="password")
        tele_token = str(st.secrets.get("TELEGRAM_TOKEN", "")).strip()
        tele_chat_id = ""
        
        if st.session_state.logged_in and db:
            user_ref = db.collection('users').document(st.session_state.user_id)
            tele_chat_id = user_ref.get().to_dict().get('telegram_chat_id', "") if user_ref.get().exists else ""
            input_chat_id = st.text_input("📱 내 텔레그램 Chat ID", value=tele_chat_id)
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

# 💡 [핵심 버그 수정] 검색 엔진 지능 고도화 (HMM, NAVER 등 영문 한국주식 찾기 오류 완벽 해결)
@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip().upper()
    if not query: return None, None
    
    try:
        # 1. 무조건 한국 거래소(KRX) 먼저 수색!
        df_krx = fdr.StockListing('KRX')
        df_krx['Name_NoSpace'] = df_krx['Name'].str.replace(" ", "").str.upper()
        
        # 1-1. 숫자 6자리 (예: 005930) 입력 시
        if query.isdigit() and len(query) == 6:
            match = df_krx[df_krx['Code'] == query]
            if not match.empty: 
                return match['Name'].values[0], query
                
        # 1-2. 한글/영문 이름 정확히 일치 (HMM, NAVER 구출)
        query_nospace = query.replace(" ", "")
        match = df_krx[df_krx['Name_NoSpace'] == query_nospace]
        if not match.empty: 
            return match['Name'].values[0], match['Code'].values[0]
            
        # 1-3. 이름 부분 일치 (가장 짧은 이름 우선)
        match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query_nospace, na=False)]
        if not match_partial.empty: 
            best = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]
            return best['Name'], best['Code']
            
    except: pass
    
    # 2. 한국에 절대 없다면, 그제야 미국 티커(AAPL 등)로 간주!
    if re.match(r'^[A-Z0-9\.]+$', query): 
        return query, query
        
    return None, None

@st.cache_data(ttl=86400)
def get_financial_summary(ticker):
    if not str(ticker).isdigit(): return "N/A (해외주식은 차트/뉴스 위주 분석)"
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
    
    # 볼린저밴드 계산
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
    
    # 스퀴즈 판별
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
tab1, tab2, tab3 = st.tabs(["📊 차트 & 타점 분석", "💼 현금 트래킹 및 AI 리밸런싱", "🔍 매수 급소 스크리너"])

# -----------------------------------------------------
# [탭 1] 차트 & 타점 분석 (HTS급 고도화)
# -----------------------------------------------------
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: 
        st.error("❌ 종목을 찾을 수 없습니다. (이름이나 코드를 다시 확인해 주세요)")
        st.stop()

    st.subheader(f"📊 {actual_name} 실시간 차트 & 타점 분석")
    with st.spinner("빅데이터 연산 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) 
        except: 
            df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) 
        
        # 2단 서브플롯 (위: 주가/보조지표, 아래: 거래량)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        
        # Row 1: 주가 및 보조지표
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Upper'], mode='lines', line=dict(color='rgba(14, 165, 233, 0.4)', width=1), name='BB 상단'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Lower'], mode='lines', line=dict(color='rgba(14, 165, 233, 0.4)', width=1), fill='tonexty', fillcolor='rgba(14, 165, 233, 0.1)', name='BB 하단'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#8b5cf6', width=1.5), name='5일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='#ef4444', width=2, dash='dash'), name='최대 매물대(60일)'), row=1, col=1)
        
        # Row 1: 매수/매도 타점 마커
        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]; b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]; s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', color='red', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매수 타점'), row=1, col=1)
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', color='blue', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매도 타점'), row=1, col=1)

        # Row 2: 거래량 막대 차트
        colors = ['#ef4444' if row['Close'] >= row['Open'] else '#3b82f6' for _, row in display_df.iterrows()]
        fig.add_trace(go.Bar(x=display_df.index, y=display_df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

        # 현재가 형광펜선 강조
        curr_price = float(df['Close'].iloc[-1])
        formatted_price = f"{int(curr_price):,}원" if str(ticker).isdigit() else f"${curr_price:,.2f}"
        fig.add_hline(y=curr_price, line_dash="dot", line_color="#10b981", line_width=2, 
                      annotation_text=f"현재가: {formatted_price}", annotation_position="right", 
                      annotation_font=dict(size=13, color="white"), annotation_bgcolor="#10b981", row=1, col=1)

        # Hovermode 'x unified' 적용
        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            xaxis2_rangeslider_visible=False,
            height=650, 
            margin=dict(l=10, r=80, t=10, b=20), 
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(size=11)),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        curr_p = float(df['Close'].iloc[-1]); entry2 = float(tech_ind['EMA15']); tar_p = curr_p + (float(tech_ind['ATR']) * 4); stop_p = curr_p - (float(tech_ind['ATR']) * 2)
        rr_1 = (tar_p - curr_p) / (curr_p - stop_p) if (curr_p - stop_p) > 0 else 0
        rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0

        c1.markdown("🎯 **추천 매수 타점**")
        c1.info(f"**1차:** {format_price(curr_p, ticker)} (돌파)\n\n**2차:** {format_price(entry2, ticker)} (눌림)")
        c2.markdown("🛡️ **목표 및 손절 라인**")
        c2.warning(f"**목표가:** {format_price(tar_p, ticker)}\n\n**손절가:** {format_price(stop_p, ticker)}")
        c3.markdown("⚖️ **타점 매력도 (손익비)**")
        c3.success(f"**현재가 진입시:** {rr_1:.1f}배\n\n**2차 진입시:** {rr_2:.1f}배 (극대화)")

        st.markdown("---")
        fin_data = get_financial_summary(ticker)
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.markdown("**☁️ 클라우드 4원칙**")
            if tech_ind:
                for rule, passed in tech_ind["Cloud_Rules"].items(): st.write(f"{'✅' if passed else '❌'} {rule}")
                rsi_val = tech_ind.get('RSI', 50)
                rsi_sig = "🔥과열" if rsi_val >= 70 else "❄️침체" if rsi_val <= 30 else "보통"
                macd_cross = "🟢골든크로스(매수)" if tech_ind.get('MACD_Cross') else "🔴데드크로스(매도)"
                bb_sig = "📉스퀴즈(응축, 시세분출 전야)" if tech_ind.get('BB_Is_Squeeze') else "📈일반 확장"
                st.info(f"**RSI (14):** {rsi_val:.1f} ({rsi_sig})  |  **MACD:** {macd_cross}\n\n**볼린저밴드:** {bb_sig}")
                st.markdown("**📅 월봉 10선 추세**")
                if tech_ind.get('Is_Above_Monthly_EMA10'): st.success(f"🟢 안전 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 돌파)")
                else: st.error(f"🔴 위험 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 이탈)")
            st.markdown("**📊 펀더멘털 (재무제표)**")
            st.caption(f"🔍 {fin_data}")
            
        with info_col2:
            st.markdown("**📰 AI 뉴스 스크랩**")
            for news in get_recent_news(actual_name)[:4]: st.write(f"• {news}")

        st.markdown("---")
        if st.button("📊 3년 백테스팅 실행", use_container_width=True):
            with st.spinner("시뮬레이션 중..."):
                bc1, bc2, bc3 = st.columns(3)
                bc1.metric("매매 횟수", f"{stats['total_trades']}회")
                bc2.metric("승률", f"{stats['win_rate']:.1f}%")
                bc3.metric("누적 수익률", f"{stats['total_return']:.1f}%")

        st.markdown("---")
        st.markdown("### 🤖 Harness 4-Agent AI 분석 엔진")
        st.caption(f"거시경제, 기술적, 기본적, 리스크 관리자가 다각도로 토론하여 **'{st.session_state.invest_style}'** 성향에 맞춘 결론을 냅니다.")
        if st.button("🚀 4-Agent 분석 실행", type="primary", use_container_width=True):
            if not gemini_api_key: st.error("위쪽 계정 설정에서 API Key를 입력하세요!"); st.stop()
            with st.spinner("4명의 AI 에이전트가 토론 중입니다... (약 10초 소요)"):
                prompt = f"""
                당신은 'Harness 4-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다. 성향: {st.session_state.invest_style}
                종목: {actual_name}, 뉴스: {get_recent_news(actual_name)[:3]}, 월봉10선: {'안전' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험'}
                RSI: {tech_ind['RSI']:.1f}, MACD: {'골든크로스' if tech_ind['MACD_Cross'] else '데드크로스'}, 손절가: {format_price(stop_p, ticker)}
                RSI 70 이상 및 MACD 데드크로스 시 강력 매도 권고. 출력 형식(JSON): {{"macroAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "technicalAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "fundamentalAgent": {{"score": 0~100 사이의 정수, "reasoning": "..."}}, "riskManager": {{"action": "매수/관망/매도", "positionSize": "비중", "reasoning": "..."}}}}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 4-Agent 분석 완료!")
                    st.markdown(f"#### 🌍 Agent 1: 거시경제 분석가 (Score: {res['macroAgent']['score']}/100)"); st.info(res['macroAgent']['reasoning'])
                    st.markdown(f"#### 📈 Agent 2: 기술적 분석가 (Score: {res['technicalAgent']['score']}/100)"); st.success(res['technicalAgent']['reasoning'])
                    st.markdown(f"#### 📰 Agent 3: 기본적 분석가 (Score: {res['fundamentalAgent']['score']}/100)"); st.warning(res['fundamentalAgent']['reasoning'])
                    st.markdown("#### 🛡️ Agent 4: 리스크 관리자 (최종 판단)"); st.error(res['riskManager']['reasoning'])
                except Exception as e: st.error(f"분석 오류: {e}")
    else:
        st.warning("⚠️ 차트 데이터를 불러오지 못했습니다. 1) 상장한 지 200일이 안 된 신규 종목이거나 2) 종목명/코드를 다시 한 번 확인해 주세요.")

# -----------------------------------------------------
# [탭 2] 현금 트래킹 및 AI 리밸런싱
# -----------------------------------------------------
with tab2:
    p_data = st.session_state.p_data
    
    st.subheader(f"💼 {st.session_state.user_id}님의 운용 장부")
    
    with st.expander("💰 자산 및 초기 자본금 설정", expanded=(p_data['initial_capital'] == 0)):
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

    st.markdown("### 📊 현금 및 계좌 잔고 현황")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("보유 예수금 (현금)", f"{int(remaining_cash):,}원")
    m2.metric("주식 투자금 (매수원금)", f"{int(total_invested):,}원")
    m3.metric("계좌 총 자산 (현금+주식)", f"{int(total_asset_value):,}원")
    m4.metric("누적 실현손익 (가계부)", f"{int(p_data['realized_profit']):,}원", delta=f"{int(total_unrealized_profit):,}원 (현재 평가손익)")

    st.markdown("---")

    if not dis_df.empty:
        v1, v2 = st.columns(2)
        with v1:
            fig_p = go.Figure(data=[go.Pie(labels=dis_df['종목명'], values=dis_df['평가금액'], hole=.4, textinfo='percent', textposition='inside')])
            fig_p.update_layout(title_text="자산 비중", height=250, margin=dict(l=10, r=10, t=40, b=10), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_p, use_container_width=True, config={'displayModeBar': False})
        with v2:
            bar_colors = ['#ef4444' if r > 0 else '#3b82f6' for r in dis_df['수익률(%)']]
            fig_b = go.Figure(data=[go.Bar(x=dis_df['종목명'], y=dis_df['수익률(%)'], marker_color=bar_colors, text=dis_df['수익률(%)'].apply(lambda x: f"{x:.1f}%"), textposition='outside')])
            fig_b.update_layout(title_text="종목별 수익률", height=250, margin=dict(l=10, r=10, t=40, b=10), xaxis=dict(showticklabels=False))
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
        st.markdown("<br>### 📋 현재 보유 종목", unsafe_allow_html=True)
        edt_df = st.data_editor(dis_df.drop(columns=['평가금액']), column_config={"종목명": st.column_config.TextColumn(disabled=True), "현재가": st.column_config.NumberColumn(disabled=True), "수익금": st.column_config.NumberColumn(disabled=True), "수익률(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True)}, hide_index=True, use_container_width=True)
        
        if str(pd.DataFrame(p_data['stocks'])[['매수단가', '수량']].fillna(0).values.tolist()) != str(edt_df[['매수단가', '수량']].fillna(0).values.tolist()):
            p_data['stocks'] = edt_df[['종목명', '매수단가', '수량']].to_dict('records')
            save_portfolio(p_data); st.rerun()
        
        st.markdown("---")
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("✨ 펀드매니저 AI 리밸런싱 (자산 배분 지시서)", use_container_width=True):
                if not gemini_api_key: st.error("API Key를 입력하세요."); st.stop()
                with st.spinner("계좌 자금 흐름과 실시간 거시경제 시황을 통합 분석 중입니다..."):
                    market_news = get_recent_news("글로벌 경제 증시 시황") + get_recent_news("미국 증시 주요 이슈")
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
# [탭 3] 매수 급소 스크리너
# -----------------------------------------------------
with tab3:
    st.subheader("🔍 매수 급소 AI 스크리너")
    mode = st.radio("모드", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"])
    send_to_telegram = st.checkbox("📱 스캔 완료 시 텔레그램 전송", value=True)
    
    if st.button("🔎 검색 실행", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier != 'VIP':
            st.markdown("<div class='paywall-box'><h4>🔒 VIP 전용</h4><p>사이드바에서 로그인 후 이용하세요.</p></div>", unsafe_allow_html=True); st.stop()
            
        with st.spinner("전체 시장 종목을 불러오는 중입니다... (1~2분 소요)"):
            if "한국 우량주" in mode: sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270"}
            elif "한국 코스피" in mode: sl = get_top_200_stocks()
            else: sl = get_us_top_stocks()
            
            res = []; bar = st.progress(0); txt = st.empty()
            
            for i, (n, c) in enumerate(sl.items()):
                txt.text(f"스캔 중... {n} ({i+1}/{len(sl)})")
                try:
                    df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=300)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                    if ind:
                        sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                        is_macd_bullish = ind['MACD_Cross']
                        is_rsi_good = (ind['RSI'] > 50) or (ind['RSI'] <= 35)
                        
                        if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and is_macd_bullish and is_rsi_good:
                            p = float(df['Close'].iloc[-1]); a = float(ind['ATR'])
                            tar_p = p + (a*4); stop_p = p - (a*2); entry2 = float(ind['EMA15'])
                            rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0
                            
                            rule_str = ", ".join([f"✅{k.split('(')[0]}" if v else f"❌{k.split('(')[0]}" for k, v in ind["Cloud_Rules"].items()])
                            
                            res.append({
                                "종목명": n, 
                                "시그널": "🔥 강력" if sc==4 else "👍 분할", 
                                "클라우드 세부조건": rule_str, 
                                "현재가": p, 
                                "2차타점": entry2, 
                                "목표가": tar_p, 
                                "손절가": stop_p, 
                                "손익비": rr_2,
                                "RSI": ind['RSI'],
                                "MACD": "골든크로스" if is_macd_bullish else "데드크로스",
                                "BB상태": "📉스퀴즈" if ind.get("BB_Is_Squeeze") else "확장"
                            })
                except: pass
                bar.progress((i+1)/len(sl))
            txt.text("✅ 스캔 완료!")
            
            if res:
                df_res = pd.DataFrame(res)
                st.dataframe(df_res, use_container_width=True, hide_index=True)
                st.download_button("📥 CSV 다운로드", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name="cloud_quant.csv", mime="text/csv")
                
                if send_to_telegram and tele_token and tele_chat_id:
                    chunks = []; msg = f"🚀 <b>클라우드 퀀트 스캔 완료</b>\n\n총 {len(res)}개 종목 발견\n\n"
                    for r in res:
                        is_krw = str(sl.get(r['종목명'], "A")).isdigit()
                        if is_krw:
                            curr_p = f"{int(r['현재가']):,}원"; tar_p = f"{int(r['목표가']):,}원"; stop_p = f"{int(r['손절가']):,}원"; entry2_p = f"{int(r['2차타점']):,}원"
                        else:
                            curr_p = f"${r['현재가']:,.2f}"; tar_p = f"${r['목표가']:,.2f}"; stop_p = f"${r['손절가']:,.2f}"; entry2_p = f"${r['2차타점']:,.2f}"

                        info = f"🔥 <b>{r['종목명']}</b> ({r['시그널']})\n"
                        info += f" └ ☁️ <b>조건:</b> {r['클라우드 세부조건']}\n"
                        info += f" └ 📊 <b>RSI:</b> {r['RSI']:.1f} | <b>MACD:</b> {r['MACD']} | <b>BB:</b> {r['BB상태']}\n"
                        info += f" └ 🎯 <b>매수:</b> 1차 {curr_p} / 2차 {entry2_p}\n"
                        info += f" └ 🎯 <b>목표:</b> {tar_p}\n"
                        info += f" └ 🛡️ <b>손절:</b> {stop_p}\n"
                        info += f" └ ⚖️ <b>손익비(매력도):</b> 2차 진입시 {r['손익비']:.1f}배 극대화\n\n"
                        
                        if len(msg) + len(info) > 3800: chunks.append(msg); msg = info
                        else: msg += info
                    chunks.append(msg)
                    for c in chunks: send_telegram_message(tele_token, tele_chat_id, c); time.sleep(0.3)
                    st.success("📱 텔레그램 전송 완료!")
            else: st.warning("월봉 10선 위 안전한 매수 타점 종목이 없습니다.")
