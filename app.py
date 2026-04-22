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
# 1. 페이지 설정 및 모바일 UX 최적화
# ==========================================
st.set_page_config(page_title="클라우드 기법 퀀트", layout="wide", page_icon="☁️", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* 💡 사이드바 여는 메뉴(Header)는 살려두고, 불필요한 우측 메뉴만 지웁니다 */
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
# 2. SaaS 회원 관리 및 포트폴리오
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_id' not in st.session_state: st.session_state.user_id = 'guest'
if 'user_tier' not in st.session_state: st.session_state.user_tier = 'Free'

st.sidebar.title("👤 내 계정 (SaaS)")
if not st.session_state.logged_in:
    st.sidebar.info("💡 체험용: ID 'vip', PW '1234'")
    login_id = st.sidebar.text_input("아이디")
    login_pw = st.sidebar.text_input("비밀번호", type="password")
    if st.sidebar.button("로그인", use_container_width=True):
        if login_id == 'vip' and login_pw == '1234':
            st.session_state.logged_in = True; st.session_state.user_id = 'vip_user'; st.session_state.user_tier = 'VIP'
            st.sidebar.success("VIP님 환영합니다!"); st.rerun()
        else:
            st.session_state.logged_in = True; st.session_state.user_id = login_id if login_id else 'user'; st.session_state.user_tier = 'Free'
            st.sidebar.success("로그인 되었습니다."); st.rerun()
else:
    st.sidebar.success(f"안녕하세요, **{st.session_state.user_id}**님!")
    st.sidebar.write(f"🌟 현재 등급: **{st.session_state.user_tier}**")
    if st.sidebar.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False; st.session_state.user_id = 'guest'; st.session_state.user_tier = 'Free'; st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("⚙️ AI 설정")
if "GEMINI_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 시스템 AI 키 연동 완료")
else:
    gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")

# 💡 텔레그램 봇 설정 사이드바 추가
st.sidebar.markdown("---")
st.sidebar.title("🔔 텔레그램 알림 설정")
if "TELEGRAM_TOKEN" in st.secrets and "TELEGRAM_CHAT_ID" in st.secrets:
    tele_token = st.secrets["TELEGRAM_TOKEN"]
    tele_chat_id = st.secrets["TELEGRAM_CHAT_ID"]
    st.sidebar.success("✅ 텔레그램 봇 연동 완료")
else:
    tele_token = st.sidebar.text_input("Telegram Bot Token", type="password", help="BotFather에서 발급받은 토큰")
    tele_chat_id = st.sidebar.text_input("Telegram Chat ID", type="password", help="내 텔레그램 고유 숫자 ID")

# 💡 텔레그램 전송 함수 강화 (에러 파악 및 안전한 HTML 방식 적용)
def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML" # 특수기호 충돌을 막기 위해 HTML 방식 사용
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            st.error(f"❌ 텔레그램 전송 실패 ({response.status_code}): {response.text}")
            return False
        return True
    except Exception as e:
        st.error(f"❌ 텔레그램 네트워크 오류: {e}")
        return False

def get_portfolio_file(): return f'portfolio_data_{st.session_state.user_id}.csv'

def load_portfolio():
    file_name = get_portfolio_file()
    if os.path.exists(file_name):
        try: return pd.read_csv(file_name)
        except: return pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    return pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df): df.to_csv(get_portfolio_file(), index=False)

if 'portfolio' not in st.session_state or 'current_user' not in st.session_state or st.session_state.current_user != st.session_state.user_id:
    st.session_state.portfolio = load_portfolio()
    st.session_state.current_user = st.session_state.user_id

# ==========================================
# 3. 데이터 수집 & 퀀트 지표 계산
# ==========================================
@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip()
    if re.match(r'^[A-Za-z]+$', query): return query.upper(), query.upper()
    try:
        df_krx = fdr.StockListing('KRX')
        if query.isdigit() and len(query) == 6:
            match = df_krx[df_krx['Code'] == query]
            if not match.empty: return match['Name'].values[0], query
        else:
            match = df_krx[df_krx['Name'] == query]
            if not match.empty: return query, match['Code'].values[0]
    except: pass
    top_stocks = {"삼성전자":"005930", "SK하이닉스":"000660", "현대차":"005380", "카카오":"035720", "NAVER":"035420", "알테오젠":"196170", "루닛":"328130", "애플":"AAPL", "테슬라":"TSLA", "엔비디아":"NVDA", "마이크로소프트":"MSFT"}
    if query in top_stocks: return query, top_stocks[query]
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5).json().get('items', [])
        if res and len(res[0]) > 0: return res[0][0][0], res[0][0][1]
    except: pass
    if query.isdigit() and len(query) == 6: return query, query
    return None, None

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        df = fdr.StockListing('KRX-MARCAP')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except: return {}

@st.cache_data(ttl=86400)
def get_us_top_stocks():
    try:
        df = fdr.StockListing('S&P500')
        top_100 = df.head(100)
        return dict(zip(top_100['Name'], top_100['Symbol']))
    except:
        return {"Apple":"AAPL", "Tesla":"TSLA", "NVIDIA":"NVDA", "Microsoft":"MSFT", "Alphabet":"GOOGL", "Amazon":"AMZN", "Meta":"META"}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    try:
        res = requests.get(f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko", timeout=5)
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
# 4. 메인 대시보드 UI (SaaS 디자인)
# ==========================================
st.markdown("<h1>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("**(일봉 클라우드 + 월봉 10선 + 터틀 손익비)** 기반 자동화 시스템")
st.markdown("---")

col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "알테오젠", "애플(AAPL)", "테슬라(TSLA)", "엔비디아(NVDA)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (또는 6자리/영문 코드)", "삼성전자")
    else: 
        stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search
        st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "💼 내 포트폴리오", "🔍 VIP 스크리너 (한/미 통합)"])

# [탭 1] 차트 분석
with tab1:
    if not gemini_api_key: st.warning("👈 왼쪽 메뉴를 열어 API Key를 입력하세요."); st.stop()
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("종목 코드를 찾을 수 없습니다."); st.stop()

    st.subheader(f"📊 {actual_name} 실시간 차트")
    with st.spinner("빅데이터 연산 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
        except: df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(90)
        fig = go.Figure(data=[go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가")])
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='magenta', width=1.5), name='5 EMA'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='yellow', width=1.5), name='15 EMA'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='black', width=2.5, dash='dot'), name='200 EMA'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='red', width=2, dash='dash'), name='최대 매물대'))
        fig.update_layout(title="최근 3개월 지표", xaxis_rangeslider_visible=False, height=350, margin=dict(l=5, r=5, t=40, b=5), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), dragmode=False)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    st.markdown("---")
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.markdown("**☁️ 클라우드 4원칙**")
        if tech_ind:
            for rule, passed in tech_ind["Cloud_Rules"].items(): st.write(f"{'✅' if passed else '❌'} {rule}")
            stop_loss = df['Close'].iloc[-1] - (tech_ind.get('ATR', 0) * 2)
            st.info(f"🛡️ **터틀 손절가:** {format_price(stop_loss, ticker)}")
            st.markdown("**📅 월봉 10선 추세**")
            if tech_ind.get('Is_Above_Monthly_EMA10'): st.success(f"🟢 안전 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 돌파)")
            else: st.error(f"🔴 위험 ({format_price(tech_ind.get('Monthly_EMA10', 0), ticker)} 이탈)")
        else: st.error("계산 불가")
    with info_col2:
        st.markdown("**📰 AI 뉴스 스크랩**")
        for news in get_recent_news(actual_name)[:4]: st.caption(f"• {news}")

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
        if st.button("🚀 클라우드 AI 정밀 분석", type="primary", use_container_width=True):
            with st.spinner("AI 분석 중... (API 제한 시 최대 30초 대기)"):
                prompt = f"""
                종목: {actual_name}, 단기 클라우드 통과: {sum(1 for v in tech_ind["Cloud_Rules"].values() if v)}/4
                월봉10선: {'안전' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험(저승사자)'}
                손절가: {format_price(stop_loss, ticker)}, 뉴스: {get_recent_news(actual_name)}
                위험 상태면 무조건 관망/매도 지시해. JSON 응답: {{"technicalAgent": {{"score": 8, "reasoning": "..."}}, "fundamentalAgent": {{"score": 6, "reasoning": "..."}}, "riskManager": {{"action": "매수", "positionSize": "20%", "reasoning": "..."}}}}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 분석 완료!")
                    c1, c2, c3 = st.columns(3)
                    with c1: st.metric("차트 점수", f"{res['technicalAgent']['score']}점"); st.caption(res['technicalAgent']['reasoning'])
                    with c2: st.metric("뉴스 점수", f"{res['fundamentalAgent']['score']}점"); st.caption(res['fundamentalAgent']['reasoning'])
                    with c3: st.metric(f"포지션: {res['riskManager']['action']}", f"비중: {res['riskManager']['positionSize']}"); st.caption(res['riskManager']['reasoning'])
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
        
        edt_df = st.data_editor(dis_df, column_config={"종목명": st.column_config.TextColumn(disabled=True), "현재가": st.column_config.NumberColumn(disabled=True), "수익금": st.column_config.NumberColumn(disabled=True), "수익률(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True)}, hide_index=True, use_container_width=True)
        if not edt_df.equals(dis_df.drop(columns=['현재가','수익금','수익률(%)'])):
            st.session_state.portfolio[['매수단가','수량']] = edt_df[['매수단가','수량']]; save_portfolio(st.session_state.portfolio); st.rerun()

        if st.button("✨ 포트폴리오 AI 진단", type="primary", use_container_width=True):
            with st.spinner("진단 중..."):
                txt = ""
                for _, r in dis_df.iterrows():
                    _, tck = get_stock_info(r['종목명']); stat = "불가"
                    if tck:
                        try:
                            df, ind = calculate_cloud_indicators(fdr.DataReader(tck, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                            if ind: stat = f"월봉10선({'안전' if ind.get('Is_Above_Monthly_EMA10') else '위험'}), 200일선 위({'O' if ind['Cloud_Rules']['주가 > 200일선'] else 'X'})"
                        except: pass
                    txt += f"- {r['종목명']}: 수익 {r['수익률(%)']:.2f}%, 상태: {stat}\n"
                
                try:
                    res = get_ai_analysis(f"월봉10선 위험이면 전량매도 권고해. [포트폴리오]\n{txt}\n응답: {{\"results\": [{{\"stock\": \"명\", \"action\": \"매도\", \"reason\": \"...\"}}]}}", gemini_api_key)
                    for i in res.get("results", []): st.info(f"**{i['stock']}** 👉 **{i['action']}** : {i['reason']}")
                except Exception as e: st.error(f"오류: {e}")
        if st.button("🗑️ 선택 삭제"): st.warning("수량을 0으로 만들면 삭제됩니다.")
    else: st.info("등록된 종목이 없습니다.")

# [탭 3] VIP 검색기
with tab3:
    st.subheader("🔍 매수 급소 AI 스크리너")
    mode = st.radio("모드", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"])
    
    send_to_telegram = st.checkbox("📱 스캔 완료 시 텔레그램으로 결과 전송", value=False)
    
    if st.button("🔎 검색 실행", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier != 'VIP':
            st.markdown("<div class='paywall-box'><h4>🔒 VIP 전용</h4><p>사이드바에서 <b>로그인</b> 후 이용하세요.</p></div>", unsafe_allow_html=True); st.stop()
            
        if "한국 우량주" in mode:
            sl = {
                "삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270", "셀트리온":"068270",
                "POSCO홀딩스":"005490", "KB금융":"105560", "NAVER":"035420", "카카오":"035720", "에코프로":"086520", "에코프로비엠":"247540",
                "두산에너빌리티":"034020", "HD현대미포":"010620", "알테오젠":"196170", "LG화학":"051910", "삼성SDI":"006400", "엔켐":"283360",
                "HLB":"028300", "한미반도체":"042700", "크래프톤":"035760", "현대모비스":"012330", "LG전자":"066570", "신한지주":"055550",
                "하나금융지주":"086790", "한국전력":"015760", "HD한국조선해양":"009540", "HD현대중공업":"329180", "한화에어로스페이스":"012450",
                "LIG넥스원":"079550", "현대로템":"064350", "삼양식품":"145990", "아모레퍼시픽":"090430", "SK이노베이션":"096770", "포스코퓨처엠":"003670",
                "두산로보틱스":"277810", "메리츠금융지주":"138040", "삼성물산":"028260", "제주반도체":"080220", "루닛":"328130"
            }
        elif "한국 코스피" in mode:
            sl = get_top_200_stocks()
        else:
            sl = get_us_top_stocks()
            
        if not sl: st.error("데이터 오류"); st.stop()
        
        res = []; bar = st.progress(0); txt = st.empty()
        for i, (n, c) in enumerate(sl.items()):
            txt.text(f"스캔 중... {n} ({i+1}/{len(sl)})")
            try:
                df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                if ind:
                    sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                    if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                        p = float(df['Close'].iloc[-1]); a = float(ind['ATR'])
                        res.append({
                            "종목명": n, 
                            "매수 시그널": "🔥 강력 매수" if sc==4 else "👍 분할 매수", 
                            "통과 개수": f"{sc}/4", 
                            "월봉 장기추세": "🟢 안전",
                            "주가 > 200일선": "✅" if ind["Cloud_Rules"]["주가 > 200일선"] else "❌",
                            "5/15일선 정배열": "✅" if ind["Cloud_Rules"]["5/15일선 정배열(돌파)"] else "❌",
                            "대량거래 돌파": "✅" if ind["Cloud_Rules"]["최대 거래량 종가 돌파"] else "❌",
                            "현재가": p, 
                            "목표가": p+(a*4), 
                            "손절가": p-(a*2),
                            "통화": "KRW" if str(c).isdigit() else "USD"
                        })
                time.sleep(0.05)
            except: pass
            bar.progress((i+1)/len(sl))
        txt.text("✅ 완료!")
        
        if res:
            df_res = pd.DataFrame(res).sort_values(by="통과 개수", ascending=False)
            
            st.dataframe(
                df_res, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "현재가": st.column_config.NumberColumn("현재가", format="%,.2f"),
                    "목표가": st.column_config.NumberColumn("목표가", format="%,.2f"),
                    "손절가": st.column_config.NumberColumn("손절가", format="%,.2f")
                }
            )
            
            st.download_button("📥 CSV 다운로드", data=df_res.to_csv(index=False).encode('utf-8-sig'), file_name=f"cloud_quant_{datetime.today().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)
            
            # 💡 텔레그램 메시지를 HTML 포맷에 맞게 재작성
            if send_to_telegram and tele_token and tele_chat_id:
                msg_text = f"🚀 <b>클라우드 퀀트 스캔 완료</b>\n\n총 {len(res)}개의 타점 종목이 발견되었습니다.\n\n"
                for r in res[:10]:
                    msg_text += f"<b>{r['종목명']}</b> ({r['매수 시그널']})\n"
                    msg_text += f"- 통과: {r['통과 개수']} | 통화: {r['통화']}\n"
                    msg_text += f"- 현재가: {r['현재가']:,.2f} | 목표: {r['목표가']:,.2f}\n\n"
                
                if len(res) > 10:
                    msg_text += f"...외 {len(res) - 10}개 종목 발견"
                    
                is_success = send_telegram_message(tele_token, tele_chat_id, msg_text)
                if is_success:
                    st.success("📱 텔레그램으로 요약 알림이 전송되었습니다!")
            elif send_to_telegram:
                st.warning("⚠️ 왼쪽 메뉴의 '텔레그램 알림 설정'에서 Token과 Chat ID를 모두 입력해야 전송됩니다.")
        else: st.warning("월봉 10선 위 안전한 종목이 없습니다.")
