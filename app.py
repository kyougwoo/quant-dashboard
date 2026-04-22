import streamlit as st
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np
import os
import time
import re

# ==========================================
# 1. 페이지 설정 및 모바일 네이티브 앱 UX 극대화
# ==========================================
st.set_page_config(page_title="클라우드 기법 퀀트", layout="wide", page_icon="☁️", initial_sidebar_state="collapsed")

# 💡 스트림릿 고유의 웹사이트 느낌(헤더, 메뉴, 푸터)을 완전히 지우고 네이티브 앱처럼 보이게 만듭니다.
st.markdown("""
<style>
    /* 상단 기본 헤더 숨기기 */
    header {visibility: hidden;}
    /* 하단 워터마크 숨기기 */
    footer {visibility: hidden;}
    /* 우측 상단 기본 메뉴 햄버거 숨기기 */
    #MainMenu {visibility: hidden;}
    
    /* 모바일 환경 최적화 */
    @media (max-width: 768px) {
        .block-container {
            padding: 1.5rem 0.5rem 1rem 0.5rem !important;
        }
        h1 {
            font-size: 1.5rem !important;
            margin-bottom: 5px !important;
            line-height: 1.3 !important;
        }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.1rem !important; }
        
        /* 탭 버튼을 모바일 화면에 꽉 차게 변경 */
        button[data-baseweb="tab"] {
            flex-grow: 1 !important;
            font-size: 0.9rem !important;
            padding: 0.5rem 0rem !important;
        }
        
        /* 모든 액션 버튼 크기 및 터치 영역 확대 */
        .stButton>button {
            width: 100% !important;
            padding: 0.8rem !important;
            font-size: 1.1rem !important;
            font-weight: 700 !important;
            border-radius: 10px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
        }
    }
    
    /* VIP 페이월 안내 박스 스타일 */
    .paywall-box {
        padding: 15px;
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        border-radius: 5px;
        margin-bottom: 15px;
        color: #856404;
    }
    
    .title-by {
        font-size: 0.55em;
        color: #4b5563;
        font-weight: 600;
        vertical-align: middle;
        margin-left: 8px;
        background-color: #f3f4f6;
        padding: 3px 8px;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        display: inline-block;
        position: relative;
        top: -3px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SaaS형 회원 관리 시스템 (Mock-up)
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = 'guest'
if 'user_tier' not in st.session_state:
    st.session_state.user_tier = 'Free'

# 로그인 사이드바
st.sidebar.title("👤 내 계정 (SaaS)")
if not st.session_state.logged_in:
    st.sidebar.info("💡 체험용 로그인: ID에 'vip', PW에 '1234'를 입력해보세요.")
    login_id = st.sidebar.text_input("아이디 (이메일)")
    login_pw = st.sidebar.text_input("비밀번호", type="password")
    
    if st.sidebar.button("로그인", use_container_width=True):
        if login_id == 'vip' and login_pw == '1234':
            st.session_state.logged_in = True
            st.session_state.user_id = 'vip_user'
            st.session_state.user_tier = 'VIP'
            st.sidebar.success("VIP님 환영합니다!")
            st.rerun()
        else:
            st.session_state.logged_in = True
            st.session_state.user_id = login_id if login_id else 'user'
            st.session_state.user_tier = 'Free'
            st.sidebar.success("로그인 되었습니다.")
            st.rerun()
else:
    st.sidebar.success(f"안녕하세요, **{st.session_state.user_id}**님!")
    st.sidebar.write(f"🌟 현재 등급: **{st.session_state.user_tier}**")
    if st.sidebar.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_id = 'guest'
        st.session_state.user_tier = 'Free'
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("⚙️ AI 엔진 설정")
if "GEMINI_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 시스템 AI 키 연동 완료")
else:
    gemini_api_key = st.sidebar.text_input("Gemini API Key (마스터)", type="password")


# 💡 포트폴리오를 유저별로 따로 저장하도록 파일명 동적 변경 (클라우드 DB화 1단계)
def get_portfolio_file():
    return f'portfolio_data_{st.session_state.user_id}.csv'

def load_portfolio():
    file_name = get_portfolio_file()
    if os.path.exists(file_name):
        try: return pd.read_csv(file_name)
        except: return pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    return pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df):
    df.to_csv(get_portfolio_file(), index=False)

if 'portfolio' not in st.session_state or 'current_user' not in st.session_state or st.session_state.current_user != st.session_state.user_id:
    st.session_state.portfolio = load_portfolio()
    st.session_state.current_user = st.session_state.user_id

# ==========================================
# 3. 데이터 수집 & 클라우드 파이썬 수식화
# ==========================================
@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip()
    try:
        df_krx = fdr.StockListing('KRX')
        if query.isdigit() and len(query) == 6:
            match = df_krx[df_krx['Code'] == query]
            if not match.empty: return match['Name'].values[0], query
        else:
            match = df_krx[df_krx['Name'] == query]
            if not match.empty: return query, match['Code'].values[0]
    except: pass
        
    top_stocks = {
        "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
        "현대차": "005380", "기아": "000270", "NAVER": "035420", "카카오": "035720", 
        "에코프로": "086520", "두산에너빌리티": "034020", "알테오젠": "196170", 
        "크래프톤": "035760", "삼양식품": "145990", "루닛": "328130"
    }
    if query in top_stocks: return query, top_stocks[query]
    
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        items = response.json().get('items', [])
        if items and len(items[0]) > 0: return items[0][0][0], items[0][0][1]
    except: pass
    
    if query.isdigit() and len(query) == 6: return query, query
    return None, None

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        df = fdr.StockListing('KRX-MARCAP')
        code_col = 'Code' if 'Code' in df.columns else 'Symbol'
        name_col = 'Name'
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        df = df[df[code_col].str.match(r'^\d{6}$')]
        df = df[~df[name_col].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        top_200 = df.head(200)
        return dict(zip(top_200[name_col], top_200[code_col]))
    except: return {}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        news_list = [item.title.text for item in items[:5] if item.title]
        return news_list if news_list else ["최신 관련 뉴스를 찾지 못했습니다."]
    except: return ["뉴스 수집 중 오류 발생"]

def calculate_cloud_indicators(df):
    if df is None or df.empty: return None, {}
        
    for col in ['Close', 'High', 'Low', 'Volume']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['Close'])
    
    if len(df) < 200: return None, {}
    
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    recent_60_df = df.tail(60)
    if recent_60_df['Volume'].sum() == 0: vol_ref_price = float(df['Close'].iloc[-1])
    else: vol_ref_price = float(recent_60_df.sort_values('Volume', ascending=False).iloc[0]['Close'])
        
    df['Vol_Ref_Price'] = vol_ref_price
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    try:
        try: monthly_close = df['Close'].resample('ME').last()
        except: monthly_close = df['Close'].resample('M').last()
        monthly_ema10 = monthly_close.ewm(span=10, adjust=False).mean()
        current_monthly_ema10 = float(monthly_ema10.iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    is_above_200 = bool(latest['Close'] > latest['EMA200'])
    is_ema_uptrend = bool(latest['EMA200'] >= prev['EMA200'])
    is_golden_cross = bool((prev['EMA5'] <= prev['EMA15']) and (latest['EMA5'] > latest['EMA15']))
    is_aligned = bool(latest['EMA5'] > latest['EMA15'])
    is_above_vol_ref = bool(latest['Close'] > vol_ref_price)
    is_above_monthly_ema10 = bool(latest['Close'] > current_monthly_ema10)
    
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']),
        "Vol_Ref_Price": float(vol_ref_price),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close'] * 0.05),
        "Monthly_EMA10": current_monthly_ema10,
        "Is_Above_Monthly_EMA10": is_above_monthly_ema10,
        "Cloud_Rules": {
            "주가 > 200일선": is_above_200, "200일선 우상향": is_ema_uptrend,
            "5/15일선 정배열(돌파)": is_golden_cross or is_aligned, "최대 거래량 종가 돌파": is_above_vol_ref
        }
    }
    return df, indicators

def run_backtest(df):
    trades = []
    position = 0
    entry_price = 0
    entry_atr = 0
    capital = 10000000 
    balance = capital

    for i in range(1, len(df)):
        prev = df.iloc[i-1]
        curr = df.iloc[i]
        if pd.isna(curr['EMA200']): continue

        if position == 0:
            if prev['EMA5'] <= prev['EMA15'] and curr['EMA5'] > curr['EMA15'] and curr['Close'] > curr['EMA200']:
                position = 1
                entry_price = curr['Close']
                entry_atr = curr['ATR'] if not pd.isna(curr['ATR']) and curr['ATR'] > 0 else (curr['Close']*0.05)
                trades.append({'date': curr.name, 'type': 'BUY', 'price': entry_price})
        elif position == 1:
            stop_loss = entry_price - (entry_atr * 2)
            target = entry_price + (entry_atr * 4)
            sell_price = 0

            if curr['Low'] <= stop_loss: sell_price = stop_loss
            elif curr['High'] >= target: sell_price = target
            elif prev['EMA5'] >= prev['EMA15'] and curr['EMA5'] < curr['EMA15']: sell_price = curr['Close']

            if sell_price > 0:
                position = 0
                profit_pct = (sell_price - entry_price) / entry_price
                balance = balance * (1 + profit_pct)
                trades.append({'date': curr.name, 'type': 'SELL', 'profit_pct': profit_pct * 100, 'balance': balance})

    sells = [t for t in trades if t['type'] == 'SELL']
    wins = [t for t in sells if t['profit_pct'] > 0]
    total_return = ((balance - capital) / capital) * 100

    return {
        'total_trades': len(sells), 'win_rate': (len(wins)/len(sells)*100) if sells else 0,
        'total_return': total_return, 'final_balance': balance
    }

@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    for attempt in range(5):
        try:
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            text = response.text.strip()
            if text.startswith("
