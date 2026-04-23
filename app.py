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

# 💡 Firebase 클라우드 DB 라이브러리 로드 시도 및 원인 파악
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
    if not FIREBASE_AVAILABLE:
        return None, f"🚨 라이브러리 누락 (구글 엔진 부품 없음)\n\n에러 상세: {FIREBASE_IMPORT_ERROR}"
    try:
        raw_s = ""
        if "FIREBASE_JSON" in st.secrets: raw_s = str(st.secrets["FIREBASE_JSON"])
        elif "firebase" in st.secrets: raw_s = str(dict(st.secrets["firebase"]))
        else: return None, "❌ [에러 2] 설정창(Secrets)이 비어있습니다."

        pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', raw_s)
        project_id = pm.group(1) if pm else None
        
        em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', raw_s)
        client_email = em.group(1) if em else None
        
        pk_start = raw_s.find("-----BEGIN PRIVATE KEY-----")
        pk_end = raw_s.find("-----END PRIVATE KEY-----")
        if pk_start == -1 or pk_end == -1: return None, "❌ [에러 3] 암호문이 잘렸거나 없습니다."
        
        pk_raw = raw_s[pk_start : pk_end + 25]
        pk_body = pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
        pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_body)
        chunks = textwrap.wrap(pk_body, 64)
        private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(chunks) + "\n-----END PRIVATE KEY-----\n"
            
        if not project_id or not client_email: return None, "❌ [에러 4] ID나 이메일이 없습니다."
            
        creds_dict = {
            "type": "service_account", "project_id": project_id, "private_key": private_key,
            "client_email": client_email, "token_uri": "https://oauth2.googleapis.com/token"
        }
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        client = firestore.Client(credentials=creds, project=project_id)
        return client, "✅ 연결 성공"
    except Exception as e:
        import traceback
        return None, f"❌ [최종 에러] 접속 거부: {e}\n\n{traceback.format_exc()}"

if 'db_client' not in st.session_state:
    client, msg = init_db()
    st.session_state.db_client = client
    st.session_state.db_msg = msg

db = st.session_state.db_client

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_id' not in st.session_state: st.session_state.user_id = 'guest'
if 'user_tier' not in st.session_state: st.session_state.user_tier = 'Free'
if 'invest_style' not in st.session_state: st.session_state.invest_style = "⚖️ 보통 (균형 추구)"

# ==========================================
# 💡 화면 최상단 계정/설정 및 투자 성향 패널!
# ==========================================
st.markdown("<h1>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("**(일봉 클라우드 + 월봉 10선 + 터틀 손익비 + RSI/MACD)** 기반 자동화 시스템")

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
                                user_data = user_doc.to_dict()
                                if user_data.get('password') == login_pw:
                                    st.session_state.logged_in = True
                                    st.session_state.user_id = login_id
                                    st.session_state.user_tier = user_data.get('tier', 'Free')
                                    st.success("로그인 성공!"); st.rerun()
                                else: st.error("❌ 비밀번호가 틀렸습니다.")
                            else:
                                tier = 'VIP' if login_id.lower() == 'vip' else 'Free'
                                user_ref.set({'password': login_pw, 'tier': tier, 'created_at': datetime.now()})
                                st.session_state.logged_in = True; st.session_state.user_id = login_id; st.session_state.user_tier = tier
                                st.success("🎉 가입/로그인 완료!"); st.rerun()
                        except Exception as e:
                            st.error(f"DB 오류 (테스트 모드 확인 요망): {e}")
                    else:
                        st.session_state.logged_in = True; st.session_state.user_id = login_id
                        st.session_state.user_tier = 'VIP' if login_id == 'vip' else 'Free'
                        st.rerun()
        else:
            st.success(f"환영합니다, **{st.session_state.user_id}**님!")
            st.write(f"🌟 현재 등급: **{st.session_state.user_tier}**")
            if st.button("로그아웃", use_container_width=True):
                st.session_state.logged_in = False; st.session_state.user_id = 'guest'; st.session_state.user_tier = 'Free'; st.rerun()
                
    with set_col:
        st.markdown("### ⚙️ 연동 및 AI 성향 설정")
        st.session_state.invest_style = st.selectbox(
            "🎯 나의 투자 성향", 
            ["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"],
            index=["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"].index(st.session_state.invest_style)
        )
        
        gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if not gemini_api_key: gemini_api_key = st.text_input("Gemini API Key", type="password")
        else: st.success("✅ AI 엔진 연동 완료")

        if db: st.success("☁️ Firebase DB 연동 완료")
        else: 
            st.warning("⚠️ 로컬 저장 모드 작동 중")
            if st.button("🔄 Firebase 연결 재시도"): del st.session_state['db_client']; st.rerun()

        tele_token = str(st.secrets.get("TELEGRAM_TOKEN", "")).strip()
        tele_chat_id = ""
        
        if st.session_state.logged_in and db:
            user_ref = db.collection('users').document(st.session_state.user_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                tele_chat_id = user_doc.to_dict().get('telegram_chat_id', "")
            
            input_chat_id = st.text_input("📱 내 텔레그램 Chat ID (알람 수신용)", value=tele_chat_id)
            if input_chat_id != tele_chat_id:
                if st.button("알림 ID 저장", use_container_width=True):
                    user_ref.update({'telegram_chat_id': input_chat_id})
                    st.success("✅ Chat ID가 저장되었습니다!")
                    time.sleep(1)
                    st.rerun()
            tele_chat_id = input_chat_id
            
            if tele_token and tele_chat_id: 
                st.success("✅ 텔레그램 알림 수신 준비 완료")
        else:
            st.info("💡 로그인하시면 알람 ID를 저장할 수 있습니다.")
            tele_chat_id = st.text_input("Telegram Chat ID", type="password").strip()

st.markdown("---")

def send_telegram_message(token, chat_id, text):
    try:
        base_url = "https://" + "api.telegram.org/bot"
        res = requests.post(f"{base_url}{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
        if res.status_code != 200: return False
        return True
    except Exception as e: return False

def load_portfolio():
    if db:
        try:
            doc = db.collection('portfolios').document(st.session_state.user_id).get()
            if doc.exists and 'stocks' in doc.to_dict(): return pd.DataFrame(doc.to_dict()['stocks'])
        except: pass
    file_name = f'portfolio_data_{st.session_state.user_id}.csv'
    if os.path.exists(file_name):
        try: return pd.read_csv(file_name)
        except: pass
    return pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df):
    if db:
        try:
            db.collection('portfolios').document(st.session_state.user_id).set({'stocks': df.to_dict('records')})
            return
        except: pass
    df.to_csv(f'portfolio_data_{st.session_state.user_id}.csv', index=False)

if 'portfolio' not in st.session_state or 'current_user' not in st.session_state or st.session_state.current_user != st.session_state.user_id:
    st.session_state.portfolio = load_portfolio()
    st.session_state.current_user = st.session_state.user_id

# ==========================================
# 3. 데이터 수집 & 퀀트 지표 계산 로직 (RSI, MACD 추가)
# ==========================================
@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip()
    if not query: return None, None
    query_no_space = query.replace(" ", "").upper()

    if re.match(r'^[A-Z0-9\.]+$', query_no_space): return query_no_space, query_no_space
    try:
        df_krx = fdr.StockListing('KRX')
        if query_no_space.isdigit() and len(query_no_space) == 6:
            match = df_krx[df_krx['Code'] == query_no_space]
            if not match.empty: return match['Name'].values[0], query_no_space
            
        df_krx['Name_NoSpace'] = df_krx['Name'].str.replace(" ", "").str.upper()
        match = df_krx[df_krx['Name_NoSpace'] == query_no_space]
        if not match.empty: return match['Name'].values[0], match['Code'].values[0]

        match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query_no_space, na=False)]
        if not match_partial.empty:
            best_match = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]
            return best_match['Name'], best_match['Code']
    except: pass

    top_stocks = {"삼성전자":"005930", "SK하이닉스":"000660", "현대차":"005380", "카카오":"035720", "NAVER":"035420", "알테오젠":"196170", "루닛":"328130", "에코프로":"086520", "에코프로비엠":"247540", "셀트리온":"068270", "LG에너지솔루션":"373220"}
    for name, code in top_stocks.items():
        if query_no_space in name.replace(" ", ""): return name, code

    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5).json().get('items', [])
        if res and len(res[0]) > 0: return res[0][0][0], res[0][0][1]
    except: pass
    return None, None

@st.cache_data(ttl=86400)
def get_financial_summary(ticker):
    if not str(ticker).isdigit(): 
        return "N/A (해외주식은 차트 및 뉴스 위주로 분석합니다)"
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        per = soup.select_one('#_per').text if soup.select_one('#_per') else "N/A"
        pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else "N/A"
        dvr = soup.select_one('#_dvr').text if soup.select_one('#_dvr') else "N/A"
        
        return f"PER: {per} / PBR: {pbr} / 배당수익률: {dvr}%"
    except:
        return "재무 데이터 수집 오류"

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        try: df = fdr.StockListing('KOSPI')
        except: df = fdr.StockListing('KRX-MARCAP')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        if 'Marcap' in df.columns: df = df.sort_values('Marcap', ascending=False)
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        res = dict(zip(df.head(200)['Name'], df.head(200)[col]))
        if len(res) > 10: return res
        raise Exception("Fetch Failed")
    except: 
        return {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "셀트리온":"068270", "KB금융":"105560", "POSCO홀딩스":"005490", "NAVER":"035420", "현대모비스":"012330", "카카오":"035720"}

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
    
    # RSI (14일)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)
    
    # MACD (12, 26, 9)
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    recent_60 = df.tail(60)
    vol_ref_price = float(df['Close'].iloc[-1]) if recent_60['Volume'].sum() == 0 else float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
    df['Vol_Ref_Price'] = vol_ref_price
    
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['ATR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1).rolling(window=14).mean()
    
    try:
        try: monthly_close = df['Close'].resample('ME').last()
        except: monthly_close = df['Close'].resample('M').last()
        current_monthly_ema10 = float(monthly_close.ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    latest = df.iloc[-1]; prev = df.iloc[-2]
    
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']),
        "Vol_Ref_Price": float(vol_ref_price), "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']),
        "MACD": float(latest['MACD']),
        "MACD_Signal": float(latest['MACD_Signal']),
        "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "Cloud_Rules": {
            "주가 > 200일선": bool(latest['Close'] > latest['EMA200']),
            "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']),
            "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']),
            "최대 거래량 종가 돌파": bool(latest['Close'] > vol_ref_price)
        }
    }
    return df, indicators

def run_backtest(df):
    trades = []; position = 0; entry_price = 0; entry_atr = 0; balance = 10000000 
    for i in range(1, len(df)):
        prev = df.iloc[i-1]; curr = df.iloc[i]
        if pd.isna(curr['EMA200']): continue
        if position == 0:
            if prev['EMA5'] <= prev['EMA15'] and curr['EMA5'] > curr['EMA15'] and curr['Close'] > curr['EMA200']:
                position = 1; entry_price = curr['Close']; entry_atr = curr['ATR'] if not pd.isna(curr['ATR']) and curr['ATR']>0 else curr['Close']*0.05
                trades.append({'type': 'BUY'})
        elif position == 1:
            stop_loss = entry_price - (entry_atr * 2); target = entry_price + (entry_atr * 4); sell_price = 0
            if curr['Low'] <= stop_loss: sell_price = stop_loss
            elif curr['High'] >= target: sell_price = target
            elif prev['EMA5'] >= prev['EMA15'] and curr['EMA5'] < curr['EMA15']: sell_price = curr['Close']
            if sell_price > 0:
                position = 0; profit_pct = (sell_price - entry_price) / entry_price; balance *= (1 + profit_pct)
                trades.append({'type': 'SELL', 'profit_pct': profit_pct * 100})
    sells = [t for t in trades if t['type'] == 'SELL']
    wins = [t for t in sells if t['profit_pct'] > 0]
    return {'total_trades': len(sells), 'win_rate': (len(wins)/len(sells)*100) if sells else 0, 'total_return': ((balance-10000000)/10000000)*100, 'final_balance': balance}

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

def get_current_price(ticker):
    try:
        df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        return float(df['Close'].iloc[-1]) if not df.empty else 0.0
    except: return 0.0

def format_price(price, ticker):
    if str(ticker).isdigit(): return f"{int(price):,}원"
    else: return f"${price:.2f}"

# ==========================================
# 4. 메인 대시보드 UI 하단부
# ==========================================
col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "알테오젠", "애플(AAPL)", "테슬라(TSLA)", "엔비디아(NVDA)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (일부만 쳐도 검색됨 / 영문 코드)", "삼성전자")
    else: 
        stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search
        st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "💼 내 포트폴리오", "🔍 VIP 스크리너 (한/미 통합)"])

# [탭 1] 차트 분석
with tab1:
    if not gemini_api_key: st.warning("☝️ 위쪽 계정 설정에서 API Key를 입력하세요."); st.stop()
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("❌ 종목을 찾을 수 없습니다. 철자를 확인하거나 띄어쓰기 없이 검색해보세요."); st.stop()

    st.subheader(f"📊 {actual_name} 실시간 차트")
    with st.spinner("빅데이터 연산 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
        except: df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(90)
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=display_df.index, 
            open=display_df['Open'], high=display_df['High'], 
            low=display_df['Low'], close=display_df['Close'], 
            name="주가",
            increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
        ))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#8b5cf6', width=1.5), name='5일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='#10b981', width=2, dash='dash'), name='최대매물대'))
        
        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            height=400, 
            margin=dict(l=10, r=10, t=10, b=20), 
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(size=11)),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickfont=dict(size=10)),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickfont=dict(size=10)),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    st.markdown("---")
    
    fin_data = get_financial_summary(ticker)
    
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.markdown("**☁️ 클라우드 4원칙**")
        if tech_ind:
            for rule, passed in tech_ind["Cloud_Rules"].items(): st.write(f"{'✅' if passed else '❌'} {rule}")
            
            st.markdown("<br>**📊 RSI & MACD (타이밍 지표)**", unsafe_allow_html=True)
            rsi_val = tech_ind.get('RSI', 50)
            rsi_sig = "🔥과열" if rsi_val >= 70 else "❄️침체" if rsi_val <= 30 else "보통"
            macd_cross = "🟢골든크로스(매수)" if tech_ind.get('MACD_Cross') else "🔴데드크로스(매도)"
            st.info(f"**RSI (14):** {rsi_val:.1f} ({rsi_sig})  |  **MACD:** {macd_cross}")

            stop_loss = df['Close'].iloc[-1] - (tech_ind.get('ATR', 0) * 2)
            st.info(f"🛡️ **터틀 손절가:** {format_price(stop_loss, ticker)}")
            
            st.markdown("**📅 월봉 10선 추세**")
            if tech_ind.get('Is_Above_Monthly_EMA10'): st.success(f"🟢 안전 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 돌파)")
            else: st.error(f"🔴 위험 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 이탈)")
        else: st.error("계산 불가")
        
        st.markdown("**📊 펀더멘털 (재무제표)**")
        st.caption(f"🔍 {fin_data}")
        
    with info_col2:
        st.markdown("**📰 AI 뉴스 스크랩**")
        for news in get_recent_news(actual_name)[:4]: st.write(f"• {news}")

    st.markdown("---")
    if st.button("📊 3년 백테스팅 실행", use_container_width=True):
        with st.spinner("시뮬레이션 중..."):
            try:
                bt_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=365*3)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
                stats = run_backtest(calculate_cloud_indicators(bt_df)[0])
                c1, c2, c3 = st.columns(3)
                c1.metric("매매 횟수", f"{stats['total_trades']}회"); c2.metric("승률", f"{stats['win_rate']:.1f}%"); c3.metric("누적 수익률", f"{stats['total_return']:.1f}%")
            except: st.error("데이터 부족")

    if df is not None and not df.empty:
        st.markdown("---")
        st.markdown("### 🤖 Harness 4-Agent AI 분석 엔진 (개인화 + 매크로 + RSI/MACD)")
        st.caption(f"거시경제, 기술적, 기본적, 리스크 관리자가 다각도로 토론하여 **'{st.session_state.invest_style}'** 성향에 맞춘 결론을 냅니다.")
        
        if st.button("🚀 4-Agent 분석 실행", type="primary", use_container_width=True):
            with st.spinner("4명의 AI 에이전트가 토론 중입니다... (약 10~20초 소요)"):
                
                macro_news_list = get_recent_news("글로벌 거시경제 금리 환율 증시")[:3]
                
                prompt = f"""
                당신은 'Harness 4-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다.
                아래 데이터를 바탕으로 4명의 에이전트(거시경제, 기술적, 기본적, 리스크 관리자)의 시각에서 심층 분석을 수행하세요.

                [사용자 투자 성향 (필독)]
                - 사용자의 성향: {st.session_state.invest_style}
                - 리스크 관리자(Agent 4)는 최종 판단 시 이 성향을 반드시 반영하여 추천 투자 비중을 조절해야 합니다. (예: 보수적이면 리스크 최소화)

                [분석 대상 데이터]
                - 종목명: {actual_name}
                - 거시경제/글로벌 동향: {macro_news_list}
                - 단기 클라우드 통과: {sum(1 for v in tech_ind["Cloud_Rules"].values() if v)}/4
                - 월봉 10선 추세: {'안전(상승추세)' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험(하락추세)'}
                - RSI (14일): {tech_ind['RSI']:.1f} ({'과열' if tech_ind['RSI'] >= 70 else '침체' if tech_ind['RSI'] <= 30 else '보통'})
                - MACD: {tech_ind['MACD']:.1f} (시그널선 상태: {'상향 돌파(골든크로스)' if tech_ind['MACD_Cross'] else '하향 이탈(데드크로스)'})
                - 터틀 손절가: {format_price(stop_loss, ticker)}
                - 펀더멘털 요약: {fin_data}
                - 개별 기업 최근 뉴스: {get_recent_news(actual_name)}
                
                [🚨 리스크 관리자(Agent 4) 절대 수칙]
                1. 매수/관망/매도의 '타이밍'은 무조건 차트(월봉 10선, 클라우드, RSI, MACD)를 기준으로만 판단하세요.
                2. 거시경제와 펀더멘털 뉴스, 그리고 사용자의 '투자 성향'을 조합하여 최종 투자 비중(Position Size, 0%~100%)을 제시하세요.
                3. 만약 RSI가 70 이상(과열)이고 MACD 시그널선이 하향 이탈(데드크로스) 상태라면, 고객 성향과 무관하게 강력한 '전량 매도' 또는 '비중 대폭 축소'를 지시하세요.
                4. 만약 RSI가 30 이하에서 탈출하며 MACD 골든크로스가 보이면, 강력한 '매수' 타점(다이버전스/페일류)으로 분석하세요.

                [출력 형식 (JSON만 응답)]
                {{
                  "macroAgent": {{
                    "score": -10부터 10 사이의 정수 (10이 강력 호황),
                    "reasoning": "거시경제 분석가 에이전트의 시장 전체 숲(금리, 환율, 시황) 기반 분석 의견 (2~3문장)"
                  }},
                  "technicalAgent": {{
                    "score": -10부터 10 사이의 정수 (10이 강력 매수),
                    "reasoning": "RSI와 MACD 다이버전스/페일류 패턴 등 차트 지표를 종합한 기술적 심층 분석 의견 (2~3문장)"
                  }},
                  "fundamentalAgent": {{
                    "score": -10부터 10 사이의 정수 (10이 강력 호재),
                    "reasoning": "기본적 분석가 에이전트의 재무제표 가치 평가 및 뉴스 모멘텀 분석 의견 (2~3문장)"
                  }},
                  "riskManager": {{
                    "action": "매수", "매도", 또는 "관망" 중 택 1,
                    "positionSize": "비중 0% ~ 100% 제시",
                    "reasoning": "앞선 세 에이전트의 의견과 RSI/MACD 절대 수칙, 사용자의 '투자 성향'을 종합하여 리스크 관리자가 내리는 최종 결론 (3~4문장)"
                  }}
                }}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 4-Agent 분석 완료!")
                    
                    st.markdown(f"#### 🌍 Agent 1: 거시경제 분석가 (Score: {res['macroAgent']['score']}/10)")
                    st.info(res['macroAgent']['reasoning'])
                    
                    st.markdown(f"#### 📈 Agent 2: 기술적 분석가 (Score: {res['technicalAgent']['score']}/10)")
                    st.success(res['technicalAgent']['reasoning'])
                    
                    st.markdown(f"#### 📰 Agent 3: 기본적 분석가 (Score: {res['fundamentalAgent']['score']}/10)")
                    st.warning(res['fundamentalAgent']['reasoning'])
                    
                    st.markdown("#### 🛡️ Agent 4: 리스크 관리자 (최종 판단)")
                    st.error(res['riskManager']['reasoning'])
                    
                    c1, c2 = st.columns(2)
                    c1.metric("최종 포지션 제안", res['riskManager']['action'])
                    c2.metric("추천 투자 비중", res['riskManager']['positionSize'])
                except Exception as e: st.error(f"오류: {e}")

# [탭 2] 포트폴리오
with tab2:
    st.subheader(f"💼 {st.session_state.user_id}님의 포트폴리오")
    with st.form("add_stock_form"):
        c1, c2 = st.columns(2); c3, c4 = st.columns(2)
        with c1: p_name = st.text_input("종목명 (또는 TSLA 등)", "현대차")
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
        total_invest = (dis_df['매수단가'] * dis_df['수량']).sum()
        total_value = dis_df['평가금액'].sum()
        total_profit = dis_df['수익금'].sum()
        total_yield = (total_profit / total_invest * 100) if total_invest > 0 else 0

        st.markdown("### 📊 내 자산 요약")
        m1, m2, m3 = st.columns(3)
        m1.metric("총 매수금액", f"{int(total_invest):,}원" if total_invest > 1000 else f"${total_invest:,.2f}")
        m2.metric("총 평가금액", f"{int(total_value):,}원" if total_value > 1000 else f"${total_value:,.2f}", f"{total_profit:,.0f}원" if total_profit > 1000 else f"${total_profit:,.2f}")
        m3.metric("총 누적 수익률", f"{total_yield:.2f}%")

        st.markdown("<br>", unsafe_allow_html=True)
        
        viz_col1, viz_col2 = st.columns(2)
        with viz_col1:
            fig_pie = go.Figure(data=[go.Pie(labels=dis_df['종목명'], values=dis_df['평가금액'], hole=.4, textinfo='percent', textposition='inside')])
            fig_pie.update_layout(title_text="자산 비중", height=250, margin=dict(l=10, r=10, t=40, b=10), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
            
        with viz_col2:
            bar_colors = ['#ef4444' if r > 0 else '#3b82f6' for r in dis_df['수익률(%)']]
            fig_bar = go.Figure(data=[go.Bar(x=dis_df['종목명'], y=dis_df['수익률(%)'], marker_color=bar_colors, text=dis_df['수익률(%)'].apply(lambda x: f"{x:.1f}%"), textposition='outside')])
            fig_bar.update_layout(title_text="종목별 수익률", height=250, margin=dict(l=10, r=10, t=40, b=10), xaxis=dict(showticklabels=False))
            st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

        edt_df = st.data_editor(dis_df.drop(columns=['평가금액']), column_config={"종목명": st.column_config.TextColumn(disabled=True), "현재가": st.column_config.NumberColumn(disabled=True), "수익금": st.column_config.NumberColumn(disabled=True), "수익률(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True)}, hide_index=True, use_container_width=True)
        
        orig_vals = st.session_state.portfolio[['매수단가', '수량']].fillna(0).values.tolist()
        new_vals = edt_df[['매수단가', '수량']].fillna(0).values.tolist()
        if str(orig_vals) != str(new_vals):
            st.session_state.portfolio['매수단가'] = edt_df['매수단가']
            st.session_state.portfolio['수량'] = edt_df['수량']
            save_portfolio(st.session_state.portfolio); st.rerun()

        st.markdown("---")
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("✨ 포트폴리오 개인화 진단", use_container_width=True):
                with st.spinner(f"'{st.session_state.invest_style}' 성향에 맞춰 진단 중..."):
                    txt = ""
                    for _, r in dis_df.iterrows():
                        _, tck = get_stock_info(r['종목명']); stat = "불가"; p_fin = "N/A"
                        if tck:
                            try:
                                df_stock, ind = calculate_cloud_indicators(fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                                if ind: stat = f"월봉10선({'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}), 200일선 위({'O' if ind['Cloud_Rules']['주가 > 200일선'] else 'X'})"
                                p_fin = get_financial_summary(tck)
                            except: pass
                        txt += f"- [{r['종목명']}] 수익률: {r['수익률(%)']:.2f}%, 차트상태: {stat}, 재무상태: {p_fin}\n"
                    
                    diag_prompt = f"""
                    당신은 최고 수준의 퀀트 투자 전략가입니다. 아래 [포트폴리오]에 포함된 개별 종목들의 상태를 진단해주세요.
                    * 핵심 수칙: 고객의 투자 성향은 '{st.session_state.invest_style}' 입니다. 이 성향을 짙게 반영하여 코멘트해주세요.
                    * 월봉10선이 '위험'인 종목은 재무 상태와 무관하게 전량매도를 강력히 권고해주세요.
                    
                    [포트폴리오 데이터]\n{txt}\n
                    [출력 형식 (JSON)]\n{{ "results": [ {{ "stock": "종목명", "action": "매수 / 관망 / 매도", "reason": "이유 1문장" }} ] }}
                    """
                    try:
                        res = get_ai_analysis(diag_prompt, gemini_api_key)
                        for i in res.get("results", []): 
                            action = i.get('action', '')
                            if "매수" in action: st.success(f"**{i['stock']}** 👉 **{action}** : {i['reason']}")
                            elif "매도" in action: st.error(f"**{i['stock']}** 👉 **{action}** : {i['reason']}")
                            else: st.warning(f"**{i['stock']}** 👉 **{action}** : {i['reason']}")
                    except Exception as e: st.error(f"진단 오류: {e}")

        with btn_col2:
            if st.button("🌅 오늘의 모닝 브리핑 생성", type="primary", use_container_width=True):
                with st.spinner("거시경제 및 시장 동향 분석 중..."):
                    try:
                        macro_news = get_recent_news("미국 기준금리 환율 거시경제")
                        market_news = get_recent_news("미국 증시 마감") + get_recent_news("국내 증시 시황") + macro_news
                        portfolio_context = ""
                        for _, r in dis_df.iterrows():
                            name = r['종목명']; profit = r['수익률(%)']; _, tck = get_stock_info(name); stat = "데이터 부족"; stop_loss_val = 0; news_list = []; p_fin = "N/A"
                            if tck:
                                try:
                                    df_stock, ind = calculate_cloud_indicators(fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                                    if ind: 
                                        stop_loss_val = float(df_stock['Close'].iloc[-1]) - (float(ind.get('ATR', 0)) * 2)
                                        stat = f"월봉10선={'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}, RSI={ind.get('RSI',50):.1f}"
                                    news_list = get_recent_news(name)[:2]
                                    p_fin = get_financial_summary(tck)
                                except: pass
                            portfolio_context += f"- [{name}] 수익률: {profit:.2f}%, 손절가: {format_price(stop_loss_val, tck)}, 지표: {stat}, 재무: {p_fin}, 뉴스: {news_list}\n"
                        
                        briefing_prompt = f"""
                        당신은 글로벌 퀀트 전략가입니다. 포트폴리오 대응 전략 (모닝 브리핑)을 JSON으로 작성해주세요.
                        * 고객의 투자 성향: '{st.session_state.invest_style}'
                        * 핵심 수칙: 매도 등 대응 타이밍은 절대적으로 '지표(차트, RSI, MACD)'에 의존하고, '재무'와 '뉴스'는 비중 조절용으로 활용하세요.
                        * 'action_plan' 작성 시 반드시 사용자의 투자 성향을 반영한 멘트를 적어주세요.
                        
                        [시장 뉴스 (거시경제 포함)]\n{market_news}\n[포트폴리오]\n{portfolio_context}\n
                        [형식]\n{{ "market_overview": "오늘 장 요약(3문장)", "stock_briefings": [ {{"stock": "종목명", "alert_level": "🟢 안전/🟡 주의/🔴 위험", "strategy": "대응 전략(2문장)"}} ], "action_plan": "투자 성향이 반영된 핵심 지침(1문장)" }}
                        """
                        res = get_ai_analysis(briefing_prompt, gemini_api_key)
                        st.success("✅ 굿모닝! 오늘의 브리핑이 도착했습니다.")
                        st.markdown("### 🌐 밤사이 시장 동향 (Market Overview)"); st.info(res.get("market_overview", ""))
                        st.markdown("### 🎯 종목별 맞춤 대응 전략")
                        for stock in res.get("stock_briefings", []):
                            alert_level = stock.get("alert_level", "🟡 주의")
                            if "안전" in alert_level: st.success(f"**{stock['stock']}** ({alert_level}) : {stock.get('strategy', '')}")
                            elif "위험" in alert_level: st.error(f"**{stock['stock']}** ({alert_level}) : {stock.get('strategy', '')}")
                            else: st.warning(f"**{stock['stock']}** ({alert_level}) : {stock.get('strategy', '')}")
                        st.markdown("### 💡 핵심 행동 지침 (Action Plan)"); st.markdown(f"> **{res.get('action_plan', '')}**")
                        
                        if tele_token and tele_chat_id:
                            briefing_msg = f"🌅 <b>모닝 브리핑</b>\n\n🌐 <b>시장 동향</b>\n{res.get('market_overview', '')}\n\n🎯 <b>대응 전략</b>\n"
                            for stock in res.get("stock_briefings", []): briefing_msg += f"- <b>{stock['stock']}</b>: {stock.get('strategy', '')}\n"
                            briefing_msg += f"\n💡 <b>지침({st.session_state.invest_style}):</b> {res.get('action_plan', '')}"
                            send_telegram_message(tele_token, tele_chat_id, briefing_msg)
                            st.toast("📱 텔레그램 전송 완료!")
                    except Exception as e: st.error(f"브리핑 오류: {e}")
                    
        if st.button("🗑️ 선택 삭제"): st.warning("수량을 0으로 만들면 삭제됩니다.")
    else: st.info("등록된 종목이 없습니다.")

# [탭 3] VIP 검색기 (RSI/MACD 필터 추가)
with tab3:
    st.subheader("🔍 매수 급소 AI 스크리너")
    mode = st.radio("모드", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"])
    send_to_telegram = st.checkbox("📱 스캔 완료 시 텔레그램 전송", value=True)
    
    if st.button("🔎 검색 실행", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier != 'VIP':
            st.markdown("<div class='paywall-box'><h4>🔒 VIP 전용</h4><p>상단 설정창에서 로그인 후 이용하세요.</p></div>", unsafe_allow_html=True); st.stop()
            
        with st.spinner("전체 시장 종목을 불러오는 중입니다... (최초 1회 수 초 소요)"):
            if "한국 우량주" in mode:
                sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270"}
            elif "한국 코스피" in mode: sl = get_top_200_stocks()
            else: sl = get_us_top_stocks()
            
        if not sl: st.error("데이터 오류"); st.stop()
        
        res = []; bar = st.progress(0); txt = st.empty()
        for i, (n, c) in enumerate(sl.items()):
            txt.text(f"스캔 중... {n} ({i+1}/{len(sl)})")
            try:
                df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                if ind:
                    sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                    
                    # 💡 [RSI / MACD 필터 적용]
                    is_macd_bullish = ind['MACD_Cross']
                    is_rsi_good = (ind['RSI'] > 50) or (ind['RSI'] <= 35) # 중기 상승이거나 완전 침체 바닥이거나
                    
                    if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and is_macd_bullish and is_rsi_good:
                        p = float(df['Close'].iloc[-1]); a = float(ind['ATR'])
                        res.append({
                            "종목명": n, 
                            "매수 시그널": "🔥 강력 매수" if sc==4 else "👍 분할 매수", 
                            "통과 개수": f"{sc}/4", 
                            "통화": "KRW" if str(c).isdigit() else "USD", 
                            "현재가": p, 
                            "목표가": p+(a*4), 
                            "손절가": p-(a*2),
                            "RSI": ind['RSI'],
                            "MACD": "골든크로스" if is_macd_bullish else "데드크로스"
                        })
                time.sleep(0.05)
            except: pass
            bar.progress((i+1)/len(sl))
        txt.text("✅ 완료!")
        
        if res:
            df_res = pd.DataFrame(res).sort_values(by="통과 개수", ascending=False)
            st.dataframe(df_res, use_container_width=True, hide_index=True, column_config={"현재가": st.column_config.NumberColumn(format="%,.2f"), "목표가": st.column_config.NumberColumn(format="%,.2f"), "손절가": st.column_config.NumberColumn(format="%,.2f"), "RSI": st.column_config.NumberColumn(format="%.1f")})
            st.download_button("📥 CSV 다운로드", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name="cloud_quant.csv", mime="text/csv")
            
            if send_to_telegram and tele_token and tele_chat_id:
                sorted_res = df_res.to_dict('records')
                chunks = []
                current_msg = f"🚀 <b>클라우드 퀀트 스캔 완료</b>\n\n총 {len(sorted_res)}개 종목 발견\n\n"
                
                for r in sorted_res:
                    if r.get('통화') == "KRW":
                        curr_p = f"{int(r['현재가']):,}원"; tar_p = f"{int(r['목표가']):,}원"; stop_p = f"{int(r['손절가']):,}원"
                    else:
                        curr_p = f"${r['현재가']:,.2f}"; tar_p = f"${r['목표가']:,.2f}"; stop_p = f"${r['손절가']:,.2f}"

                    stock_info = f"<b>{r['종목명']}</b> ({r['매수 시그널']})\n"
                    stock_info += f"- 통과: {r['통과 개수']}\n"
                    stock_info += f" └ 📊 RSI: {r['RSI']:.1f} | MACD: {r['MACD']}\n"
                    stock_info += f" └ 💵 현재가: {curr_p}\n"
                    stock_info += f" └ 🎯 목표가: {tar_p}\n"
                    stock_info += f" └ 🛡️ 손절가: {stop_p}\n\n"
                    
                    if len(current_msg) + len(stock_info) > 3800: 
                        chunks.append(current_msg); current_msg = stock_info
                    else: current_msg += stock_info
                        
                if current_msg: chunks.append(current_msg)
                
                is_success = True
                for chunk in chunks:
                    if not send_telegram_message(tele_token, tele_chat_id, chunk): is_success = False
                    time.sleep(0.3)
                if is_success: st.success("📱 텔레그램 전송 완료!")
        else: st.warning("월봉 10선 위 안전한 매수 타점 종목이 없습니다.")
