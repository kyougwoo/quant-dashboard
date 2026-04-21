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
# 1. 페이지 설정 및 모바일 UI 최적화 / 영구 저장
# ==========================================
st.set_page_config(page_title="클라우드 기법 퀀트 대시보드", layout="wide", page_icon="☁️")

st.markdown("""
<style>
/* 💡 모바일 최적화 CSS 강화: 상단 겹침 방지 및 여백 확보 */
@media (max-width: 768px) {
    .block-container {
        padding: 3.5rem 0.5rem 2rem 0.5rem !important;
    }
    h1 {
        font-size: 1.4rem !important;
        margin-bottom: 10px !important;
        line-height: 1.3 !important;
    }
    h2 {
        font-size: 1.2rem !important;
    }
    h3 {
        font-size: 1.1rem !important;
    }
    .stButton>button {
        width: 100% !important;
        padding: 0.75rem !important;
        font-weight: bold !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
}
/* 타이틀 옆 by 지후아빠 스타일 */
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

PORTFOLIO_FILE = 'portfolio_data.csv'

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            return pd.read_csv(PORTFOLIO_FILE)
        except:
            return pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    return pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df):
    df.to_csv(PORTFOLIO_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# ==========================================
# 사이드바 설정
# ==========================================
st.sidebar.title("⚙️ 시스템 설정")

if "GEMINI_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 시스템에 API 키가 연동되었습니다.")
else:
    gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Google AI Studio 발급 키")

# ==========================================
# 2. 데이터 수집 & 클라우드/월봉 10선 파이썬 수식화
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
        "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
        "셀트리온": "068270", "POSCO홀딩스": "005490", "KB금융": "105560",
        "NAVER": "035420", "카카오": "035720", "에코프로": "086520",
        "에코프로비엠": "247540", "두산에너빌리티": "034020", "HD현대미포": "010620",
        "알테오젠": "196170", "LG화학": "051910", "삼성SDI": "006400",
        "엔켐": "283360", "HLB": "028300", "한미반도체": "042700",
        "크래프톤": "035760", "현대모비스": "012330", "LG전자": "066570",
        "신한지주": "055550", "하나금융지주": "086790", "한국전력": "015760",
        "HD한국조선해양": "009540", "HD현대중공업": "329180", "한화에어로스페이스": "012450",
        "LIG넥스원": "079550", "현대로템": "064350", "삼양식품": "145990",
        "아모레퍼시픽": "090430", "SK이노베이션": "096770", "포스코퓨처엠": "003670",
        "두산로보틱스": "277810", "메리츠금융지주": "138040", "삼성물산": "028260",
        "전진건설로봇": "079900", "아난티": "025980", "제주반도체": "080220", 
        "루닛": "328130", "유니슨": "018000", "영풍": "000670", "인스코비": "006490"
    }
    if query in top_stocks: return query, top_stocks[query]
    for name, code in top_stocks.items():
        if query == code: return name, code
        
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5)
        items = response.json().get('items', [])
        if items and len(items[0]) > 0: return items[0][0][0], items[0][0][1]
    except: pass
    
    if query.isdigit() and len(query) == 6: return query, query
    return None, None

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    """시가총액 상위 200종목 가져오기 (이상한 ETF, ETN, 스팩주 완벽 필터링 적용)"""
    try:
        df = fdr.StockListing('KRX-MARCAP')
        code_col = 'Code' if 'Code' in df.columns else 'Symbol'
        name_col = 'Name'
        
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        df = df[df[code_col].str.match(r'^\d{6}$')]
        df = df[~df[name_col].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR|ARIRANG|HANARO|KOSEF', na=False)]
        
        top_200 = df.head(200)
        return dict(zip(top_200[name_col], top_200[code_col]))
    except Exception as e:
        try:
            df = fdr.StockListing('KRX')
            code_col = 'Code' if 'Code' in df.columns else 'Symbol'
            name_col = 'Name'
            
            df[code_col] = df[code_col].astype(str).str.zfill(6)
            df = df[df[code_col].str.match(r'^\d{6}$')]
            df = df[~df[name_col].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR|ARIRANG|HANARO|KOSEF', na=False)]
            
            marcap_col = None
            for col in ['Marcap', 'MarketCap', '시가총액']:
                if col in df.columns:
                    marcap_col = col
                    break
                    
            if marcap_col:
                if df[marcap_col].dtype == 'object':
                    df[marcap_col] = df[marcap_col].str.replace(',', '')
                df[marcap_col] = pd.to_numeric(df[marcap_col], errors='coerce')
                df = df.sort_values(marcap_col, ascending=False)
                
            top_200 = df.head(200)
            return dict(zip(top_200[name_col], top_200[code_col]))
        except:
            return {}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        news_list = [item.title.text for item in items[:5] if item.title]
        return news_list if news_list else ["최신 관련 뉴스를 찾지 못했습니다."]
    except:
        return ["뉴스 수집 중 오류 발생"]

def calculate_cloud_indicators(df):
    """에러가 발생하지 않는 방탄 설계 + 월봉 10선(성승현 작가 기법) 추가"""
    if df is None or df.empty: 
        return None, {}
        
    for col in ['Close', 'High', 'Low', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['Close'])
    
    if len(df) < 200: 
        return None, {}
    
    # 1. 일봉 클라우드 기법 
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    recent_60_df = df.tail(60)
    
    if recent_60_df['Volume'].sum() == 0:
        vol_ref_price = float(df['Close'].iloc[-1])
    else:
        max_vol_row = recent_60_df.sort_values('Volume', ascending=False).iloc[0]
        vol_ref_price = float(max_vol_row['Close'])
        
    df['Vol_Ref_Price'] = vol_ref_price
    
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    # 💡 2. 월봉 10선 (Monthly 10-EMA) 계산 로직 추가
    try:
        try:
            monthly_close = df['Close'].resample('ME').last()
        except:
            monthly_close = df['Close'].resample('M').last()
            
        monthly_ema10 = monthly_close.ewm(span=10, adjust=False).mean()
        current_monthly_ema10 = float(monthly_ema10.iloc[-1])
    except:
        current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    is_above_200 = bool(latest['Close'] > latest['EMA200'])
    is_ema_uptrend = bool(latest['EMA200'] >= prev['EMA200'])
    is_golden_cross = bool((prev['EMA5'] <= prev['EMA15']) and (latest['EMA5'] > latest['EMA15']))
    is_aligned = bool(latest['EMA5'] > latest['EMA15'])
    is_above_vol_ref = bool(latest['Close'] > vol_ref_price)
    
    is_above_monthly_ema10 = bool(latest['Close'] > current_monthly_ema10)
    
    indicators = {
        "EMA5": float(latest['EMA5']), 
        "EMA15": float(latest['EMA15']), 
        "EMA200": float(latest['EMA200']),
        "Vol_Ref_Price": float(vol_ref_price),
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close'] * 0.05),
        "Monthly_EMA10": current_monthly_ema10,
        "Is_Above_Monthly_EMA10": is_above_monthly_ema10,
        "Cloud_Rules": {
            "주가 > 200일선": is_above_200,
            "200일선 우상향": is_ema_uptrend,
            "5/15일선 정배열(돌파)": is_golden_cross or is_aligned,
            "최대 거래량 종가 돌파": is_above_vol_ref
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

            if curr['Low'] <= stop_loss:
                sell_price = stop_loss
            elif curr['High'] >= target:
                sell_price = target
            elif prev['EMA5'] >= prev['EMA15'] and curr['EMA5'] < curr['EMA15']:
                sell_price = curr['Close']

            if sell_price > 0:
                position = 0
                profit_pct = (sell_price - entry_price) / entry_price
                balance = balance * (1 + profit_pct)
                trades.append({'date': curr.name, 'type': 'SELL', 'profit_pct': profit_pct * 100, 'balance': balance})

    sells = [t for t in trades if t['type'] == 'SELL']
    wins = [t for t in sells if t['profit_pct'] > 0]
    total_sells = len(sells)
    win_rate = (len(wins) / total_sells * 100) if total_sells > 0 else 0
    total_return = ((balance - capital) / capital) * 100

    return {
        'total_trades': total_sells,
        'win_rate': win_rate,
        'total_return': total_return,
        'final_balance': balance
    }

# 💡 복구 완료: AI 호출 무적의 방탄 코드 적용 (잘림 현상 수정본)
@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    for attempt in range(5):
        try:
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            text = response.text.strip()
            
            # AI가 가끔 JSON 형식을 어기고 마크다운을 씌워서 주는 버그 원천 차단
            if text.startswith("
