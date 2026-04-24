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
import ast
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

# ==========================================
# 1. 페이지 설정 및 모바일 UX 최적화
# ==========================================
st.set_page_config(page_title="클라우드 퀀트 PRO", layout="wide", page_icon="☁️", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background-color: transparent !important;}
    @media (max-width: 768px) {
        .block-container { padding: 3rem 0.5rem 2rem 0.5rem !important; }
        h1 { font-size: 1.4rem !important; margin-bottom: 10px !important; line-height: 1.3 !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.1rem !important; }
        button[data-baseweb="tab"] { flex-grow: 1 !important; font-size: 0.9rem !important; padding: 0.5rem 0rem !important; }
        .stButton>button { width: 100% !important; padding: 0.8rem !important; font-size: 1.1rem !important; font-weight: 700 !important; border-radius: 10px !important; }
        [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    }
    .paywall-box { padding: 15px; background-color: #fff3cd; border-left: 5px solid #ffc107; border-radius: 5px; margin-bottom: 15px; color: #856404; }
    .title-by { font-size: 0.55em; color: #4b5563; font-weight: 600; vertical-align: middle; margin-left: 8px; background-color: #f3f4f6; padding: 3px 8px; border-radius: 12px; border: 1px solid #e5e7eb; display: inline-block; position: relative; top: -3px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Firebase DB 연결 및 전역 세션 관리
# ==========================================
def init_db():
    if not FIREBASE_AVAILABLE: return None, f"🚨 라이브러리 누락 (구글 엔진 부품 없음)\n\n에러 상세: {FIREBASE_IMPORT_ERROR}"
    try:
        raw_s = ""
        if "FIREBASE_JSON" in st.secrets: raw_s = str(st.secrets["FIREBASE_JSON"])
        elif "firebase" in st.secrets: raw_s = str(dict(st.secrets["firebase"]))
        else: return None, "❌ 설정창(Secrets)이 비어있습니다."

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

# ==========================================
# 💡 상단 계정/설정 패널
# ==========================================
st.markdown("<h1>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("**(일봉 클라우드 + 월봉 10선 + 1/2차 타점 + 터틀 손익비 + RSI/MACD)**")

with st.expander("👤 내 계정 및 시스템 설정 (모바일은 여기를 눌러주세요!)", expanded=not st.session_state.logged_in):
    acc_col, set_col = st.columns([1, 1])
    with acc_col:
        st.markdown("### 👤 계정 관리")
        if not st.session_state.logged_in:
            st.info("💡 처음 로그인 시 자동으로 가입됩니다.")
            login_id = st.text_input("아이디 (이메일)")
            login_pw = st.text_input("비밀번호", type="password")
            if st.button("로그인 / 회원가입", use_container_width=True):
                if login_id and login_pw:
                    if db:
                        try:
                            user_ref = db.collection('users').document(login_id)
                            user_doc = user_ref.get()
                            if user_doc.exists:
                                if user_doc.to_dict().get('password') == login_pw:
                                    st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, user_doc.to_dict().get('tier', 'Free')
                                    st.rerun()
                                else: st.error("❌ 비밀번호가 틀렸습니다.")
                            else:
                                tier = 'VIP' if login_id.lower() == 'vip' else 'Free'
                                user_ref.set({'password': login_pw, 'tier': tier, 'created_at': datetime.now()})
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, tier; st.rerun()
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
    if db:
        try:
            doc = db.collection('portfolios').document(st.session_state.user_id).get()
            if doc.exists and 'stocks' in doc.to_dict(): return pd.DataFrame(doc.to_dict()['stocks'])
        except: pass
    if os.path.exists(f'portfolio_data_{st.session_state.user_id}.csv'): return pd.read_csv(f'portfolio_data_{st.session_state.user_id}.csv')
    return pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df):
    if db:
        try: db.collection('portfolios').document(st.session_state.user_id).set({'stocks': df.to_dict('records')}); return
        except: pass
    df.to_csv(f'portfolio_data_{st.session_state.user_id}.csv', index=False)

if 'portfolio' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.portfolio, st.session_state.current_user = load_portfolio(), st.session_state.user_id

# ==========================================
# 3. 데이터 수집 및 연산 로직
# ==========================================
@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip().upper()
    if not query: return None, None
    if re.match(r'^[A-Z0-9\.]+$', query): return query, query
    try:
        df_krx = fdr.StockListing('KRX'); df_krx['Name_NoSpace'] = df_krx['Name'].str.replace(" ", "").str.upper()
        if query.isdigit() and len(query) == 6 and not df_krx[df_krx['Code'] == query].empty: return df_krx[df_krx['Code'] == query]['Name'].values[0], query
        match = df_krx[df_krx['Name_NoSpace'] == query.replace(" ", "")]
        if not match.empty: return match['Name'].values[0], match['Code'].values[0]
        match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query.replace(" ", ""), na=False)]
        if not match_partial.empty: best = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]; return best['Name'], best['Code']
    except: pass
    return None, None

@st.cache_data(ttl=86400)
def get_financial_summary(ticker):
    if not str(ticker).isdigit(): return "N/A (해외주식은 차트 및 뉴스 위주로 분석합니다)"
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        per = soup.select_one('#_per').text if soup.select_one('#_per') else "N/A"
        pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else "N/A"
        dvr = soup.select_one('#_dvr').text if soup.select_one('#_dvr') else "N/A"
        return f"PER: {per} / PBR: {pbr} / 배당수익률: {dvr}%"
    except: return "재무 데이터 수집 오류"

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        df = fdr.StockListing('KOSPI')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except: return {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380"}

@st.cache_data(ttl=86400)
def get_us_top_stocks():
    try:
        df = fdr.StockListing('S&P500')
        top_100 = df.head(100)
        return dict(zip(top_100['Name'], top_100['Symbol']))
    except: return {"Apple":"AAPL", "Tesla":"TSLA", "NVIDIA":"NVDA", "Microsoft":"MSFT", "Alphabet":"GOOGL", "Amazon":"AMZN", "Meta":"META"}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    try:
        base_url = "https://" + "news.google.com/rss/search?q="
        res = requests.get(f"{base_url}{keyword}&hl=ko&gl=KR&ceid=KR:ko", timeout=5)
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:5] if item.title]
    except: return ["뉴스 수집 오류"]

def format_price(price, ticker):
    if str(ticker).isdigit(): return f"{int(price):,}원"
    else: return f"${price:,.2f}"

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
            err = str(e).lower()
            if "429" in err or "quota" in err:
                if attempt < 4:
                    match = re.search(r'retry in (\d+\.?\d*)s', err)
                    time.sleep((float(match.group(1)) + 1.0) if match else 15.0)
                    continue
            elif "json" in err or "expecting value" in err:
                if attempt < 4: time.sleep(2); continue
            raise e

def calculate_cloud_indicators(df):
    if df is None or df.empty: return None, {}
    df = df.dropna(subset=['Close'])
    if len(df) < 200: return None, {}
    
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['Vol_Ref_Price'] = float(df['Close'].iloc[-1]) if df.tail(60)['Volume'].sum() == 0 else float(df.tail(60).sort_values('Volume', ascending=False).iloc[0]['Close'])
    df['ATR'] = df[['High', 'Low', 'Close']].apply(lambda x: max(x['High']-x['Low'], abs(x['High']-df['Close'].shift(1).loc[x.name]), abs(x['Low']-df['Close'].shift(1).loc[x.name])), axis=1).rolling(14).mean()
    
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest, prev = df.iloc[-1], df.iloc[-2]
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']),
        "Vol_Ref_Price": float(latest['Vol_Ref_Price']), "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), "MACD": float(latest['MACD']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']), "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']), "최대 거래량 종가 돌파": bool(latest['Close'] > latest['Vol_Ref_Price'])}
    }
    return df, indicators

def run_backtest_with_markers(df):
    trades = []; position = 0; entry_price = 0; entry_atr = 0; balance = 10000000 
    buy_dates=[]; buy_prices=[]; sell_dates=[]; sell_prices=[]
    
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

# ==========================================
# 4. 메인 대시보드 UI
# ==========================================
col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "알테오젠", "애플(AAPL)", "테슬라(TSLA)", "엔비디아(NVDA)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (일부만 쳐도 검색됨 / 영문 코드)", "삼성전자")
    else: stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search; st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "💼 내 포트폴리오", "🔍 VIP 스크리너 (한/미 통합)"])

# -----------------------------------------------------
# [탭 1] 차트 분석
# -----------------------------------------------------
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("❌ 종목을 찾을 수 없습니다."); st.stop()

    st.subheader(f"📊 {actual_name} 실시간 차트 & 타점 분석")
    with st.spinner("빅데이터 연산 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) 
        except: df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) 
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#8b5cf6', width=1.5), name='5일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선'))
        
        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]; b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]; s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', color='red', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매수 타점'))
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', color='blue', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매도 타점'))

        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=10, r=10, t=10, b=20), legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        curr_p = float(df['Close'].iloc[-1])
        entry2 = float(tech_ind['EMA15'])
        tar_p = curr_p + (float(tech_ind['ATR']) * 4)
        stop_p = curr_p - (float(tech_ind['ATR']) * 2)
        
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
                st.info(f"**RSI (14):** {rsi_val:.1f} ({rsi_sig})  |  **MACD:** {macd_cross}")
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
            with st.spinner("4명의 AI 에이전트가 토론 중입니다... (약 10~20초 소요)"):
                macro_news_list = get_recent_news("글로벌 거시경제 금리 환율 증시")[:3]
                prompt = f"""
                당신은 'Harness 4-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다.
                아래 데이터를 바탕으로 4명의 에이전트(거시경제, 기술적, 기본적, 리스크 관리자)의 시각에서 심층 분석을 수행하세요.

                [사용자 투자 성향]: {st.session_state.invest_style}

                [분석 대상 데이터]
                - 종목명: {actual_name}
                - 거시경제/글로벌 동향: {macro_news_list}
                - 단기 클라우드 통과: {sum(1 for v in tech_ind["Cloud_Rules"].values() if v)}/4
                - 월봉 10선 추세: {'안전(상승추세)' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험(하락추세)'}
                - RSI (14일): {tech_ind['RSI']:.1f}
                - MACD 시그널: {'상향 돌파(골든크로스)' if tech_ind['MACD_Cross'] else '하향 이탈(데드크로스)'}
                - 손절가: {format_price(stop_p, ticker)}
                - 펀더멘털 요약: {fin_data}
                - 개별 기업 최근 뉴스: {get_recent_news(actual_name)}
                
                [🚨 리스크 관리자 절대 수칙]
                RSI 70 이상이고 MACD 하향 이탈 시 매도/비중 축소 강력 권고. RSI 30 이하 탈출 시 매수 타점 분석.
                
                [출력 형식 (JSON만 응답)]
                {{
                  "macroAgent": {{"score": 정수(-10~10), "reasoning": "거시경제 분석 (2~3문장)"}},
                  "technicalAgent": {{"score": 정수(-10~10), "reasoning": "차트 및 RSI/MACD 지표 분석 (2~3문장)"}},
                  "fundamentalAgent": {{"score": 정수(-10~10), "reasoning": "재무제표 및 뉴스 모멘텀 분석 (2~3문장)"}},
                  "riskManager": {{"action": "매수", "매도", 또는 "관망", "positionSize": "비중 0% ~ 100%", "reasoning": "최종 결론 (3~4문장)"}}
                }}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 4-Agent 분석 완료!")
                    st.markdown(f"#### 🌍 Agent 1: 거시경제 분석가 (Score: {res['macroAgent']['score']}/10)"); st.info(res['macroAgent']['reasoning'])
                    st.markdown(f"#### 📈 Agent 2: 기술적 분석가 (Score: {res['technicalAgent']['score']}/10)"); st.success(res['technicalAgent']['reasoning'])
                    st.markdown(f"#### 📰 Agent 3: 기본적 분석가 (Score: {res['fundamentalAgent']['score']}/10)"); st.warning(res['fundamentalAgent']['reasoning'])
                    st.markdown("#### 🛡️ Agent 4: 리스크 관리자 (최종 판단)"); st.error(res['riskManager']['reasoning'])
                    
                    cc1, cc2 = st.columns(2)
                    cc1.metric("최종 포지션 제안", res['riskManager']['action'])
                    cc2.metric("추천 투자 비중", res['riskManager']['positionSize'])
                except Exception as e: st.error(f"분석 오류: {e}")

# -----------------------------------------------------
# [탭 2] 포트폴리오
# -----------------------------------------------------
with tab2:
    st.subheader(f"💼 {st.session_state.user_id}님의 포트폴리오")
    with st.form("add_stock_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: p_name = st.text_input("종목명 (미국주식 포함)", "현대차")
        with c2: p_price = st.number_input("매수 단가 (원/달러)", min_value=0.0, step=1.0)
        with c3: p_qty = st.number_input("수량", min_value=1.0, step=1.0)
        with c4: st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True); submitted = st.form_submit_button("➕ 추가", use_container_width=True)
        if submitted:
            an, _ = get_stock_info(p_name)
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, pd.DataFrame({'종목명': [an if an else p_name], '매수단가': [p_price], '수량': [p_qty]})], ignore_index=True)
            save_portfolio(st.session_state.portfolio); st.rerun()

    if not st.session_state.portfolio.empty:
        dis_df = st.session_state.portfolio.copy()
        prices=[]; profs=[]; rates=[]
        for _, r in dis_df.iterrows():
            _, tck = get_stock_info(r['종목명'])
            p = get_current_price(tck) if tck else 0.0
            prof = (p - r['매수단가']) * r['수량']; rate = (prof / (r['매수단가']*r['수량']) * 100) if r['매수단가']>0 else 0
            prices.append(p); profs.append(prof); rates.append(rate)
        dis_df['현재가'] = prices; dis_df['수익금'] = profs; dis_df['수익률(%)'] = rates
        dis_df['평가금액'] = np.array(prices) * dis_df['수량'].astype(float)
        
        st.markdown("### 📊 내 자산 요약")
        m1, m2, m3 = st.columns(3)
        total_inv = (dis_df['매수단가'] * dis_df['수량']).sum()
        total_val = dis_df['평가금액'].sum()
        total_prof = dis_df['수익금'].sum()
        m1.metric("총 매수금액", f"{int(total_inv):,}원" if total_inv > 1000 else f"${total_inv:,.2f}"); m2.metric("총 평가금액", f"{int(total_val):,}원" if total_val > 1000 else f"${total_val:,.2f}", f"{total_prof:,.0f}원" if total_prof > 1000 else f"${total_prof:,.2f}"); m3.metric("총 누적 수익률", f"{(total_prof/total_inv*100) if total_inv>0 else 0:.2f}%")
        st.markdown("<br>", unsafe_allow_html=True)
        
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

        edt_df = st.data_editor(dis_df.drop(columns=['평가금액']), column_config={"종목명": st.column_config.TextColumn(disabled=True), "현재가": st.column_config.NumberColumn(disabled=True), "수익금": st.column_config.NumberColumn(disabled=True), "수익률(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True)}, hide_index=True, use_container_width=True)
        
        if str(st.session_state.portfolio[['매수단가', '수량']].fillna(0).values.tolist()) != str(edt_df[['매수단가', '수량']].fillna(0).values.tolist()):
            st.session_state.portfolio[['매수단가', '수량']] = edt_df[['매수단가', '수량']]; save_portfolio(st.session_state.portfolio); st.rerun()

        st.markdown("---")
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("✨ 포트폴리오 개인화 진단", use_container_width=True):
                if not gemini_api_key: st.error("API Key를 입력하세요."); st.stop()
                with st.spinner("진단 중..."):
                    txt = ""
                    for _, r in dis_df.iterrows():
                        _, tck = get_stock_info(r['종목명']); stat = "불가"; p_fin = "N/A"
                        if tck:
                            try:
                                _, ind = calculate_cloud_indicators(fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                                if ind: stat = f"월봉10선({'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}), 200일선 위({'O' if ind['Cloud_Rules']['주가 > 200일선'] else 'X'})"
                                p_fin = get_financial_summary(tck)
                            except: pass
                        txt += f"- [{r['종목명']}] 수익률: {r['수익률(%)']:.2f}%, 상태: {stat}, 재무: {p_fin}\n"
                    try:
                        diag_prompt = f"당신은 퀀트 전략가입니다. 고객 투자 성향: '{st.session_state.invest_style}'. 월봉10선 위험이면 재무 무관 전량매도 강력 권고하세요. [포트폴리오]\n{txt}\n[출력 형식 (JSON)]\n{{ \"results\": [ {{ \"stock\": \"종목명\", \"action\": \"매수 / 관망 / 매도\", \"reason\": \"이유 1문장\" }} ] }}"
                        res = get_ai_analysis(diag_prompt, gemini_api_key)
                        for i in res.get("results", []): 
                            if "매수" in i['action']: st.success(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                            elif "매도" in i['action']: st.error(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                            else: st.warning(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
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
                    
        if st.button("🗑️ 선택 삭제"): st.warning("수량을 0으로 만들면 삭제됩니다.")
    else: st.info("등록된 종목이 없습니다.")

# -----------------------------------------------------
# [탭 3] VIP 검색기
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
                            
                            # 💡 [업그레이드] 세부 합격 여부 분해
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
                                "MACD": "골든크로스" if is_macd_bullish else "데드크로스"
                            })
                except: pass
                bar.progress((i+1)/len(sl))
            txt.text("✅ 스캔 완료!")
            
            if res:
                # 💡 [업그레이드] 불필요했던 "통화", "통과" 열을 삭제하고 세부조건 적용
                df_res = pd.DataFrame(res)
                st.dataframe(df_res, use_container_width=True, hide_index=True)
                st.download_button("📥 CSV 다운로드", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name="cloud_quant.csv", mime="text/csv")
                
                if send_to_telegram and tele_token and tele_chat_id:
                    chunks = []; msg = f"🚀 <b>클라우드 퀀트 스캔 완료</b>\n\n총 {len(res)}개 종목 발견\n\n"
                    for r in res:
                        # 💡 [복구] 한국 주식은 '원', 미국 주식은 달러 '$' 표시 분리
                        if "KRW" in str(sl.get(r['종목명'], "")): # 통화 열이 사라졌으므로 여기서 판단
                            pass # 위에서 KRW/USD 구분이 사라졌기 때문에 통일
                        # 가격 포맷팅 (원화/달러 구분)
                        is_krw = str(sl.get(r['종목명'], "A")).isdigit()
                        if is_krw:
                            curr_p = f"{int(r['현재가']):,}원"; tar_p = f"{int(r['목표가']):,}원"; stop_p = f"{int(r['손절가']):,}원"; entry2_p = f"{int(r['2차타점']):,}원"
                        else:
                            curr_p = f"${r['현재가']:,.2f}"; tar_p = f"${r['목표가']:,.2f}"; stop_p = f"${r['손절가']:,.2f}"; entry2_p = f"${r['2차타점']:,.2f}"

                        info = f"🔥 <b>{r['종목명']}</b> ({r['시그널']})\n"
                        info += f" └ ☁️ <b>조건:</b> {r['클라우드 세부조건']}\n"
                        info += f" └ 📊 <b>RSI:</b> {r['RSI']:.1f} | <b>MACD:</b> {r['MACD']}\n"
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
