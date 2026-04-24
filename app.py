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

st.markdown("<h1>☁️ 클라우드 퀀트 PRO<span class='title-by'>by 지후아빠</span></h1>", unsafe_allow_html=True)
st.markdown("**(일봉 클라우드 + 월봉 10선 + 터틀 손익비 + RSI/MACD + 타점 분석)**")

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
                        user_ref = db.collection('users').document(login_id)
                        if user_ref.get().exists and user_ref.get().to_dict().get('password') == login_pw:
                            st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, user_ref.get().to_dict().get('tier', 'Free')
                            st.rerun()
                        elif not user_ref.get().exists:
                            tier = 'VIP' if login_id.lower() == 'vip' else 'Free'
                            user_ref.set({'password': login_pw, 'tier': tier, 'created_at': datetime.now()})
                            st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, tier
                            st.rerun()
                    else:
                        st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, 'VIP' if login_id == 'vip' else 'Free'
                        st.rerun()
        else:
            st.success(f"환영합니다, **{st.session_state.user_id}**님!")
            if st.button("로그아웃", use_container_width=True):
                st.session_state.logged_in, st.session_state.user_id = False, 'guest'; st.rerun()
                
    with set_col:
        st.markdown("### ⚙️ 설정")
        st.session_state.invest_style = st.selectbox("🎯 나의 투자 성향", ["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"], index=["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"].index(st.session_state.invest_style))
        gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", st.text_input("Gemini API Key", type="password"))).strip()
        tele_token = str(st.secrets.get("TELEGRAM_TOKEN", "")).strip()
        tele_chat_id = ""
        if st.session_state.logged_in and db:
            user_ref = db.collection('users').document(st.session_state.user_id)
            tele_chat_id = user_ref.get().to_dict().get('telegram_chat_id', "") if user_ref.get().exists else ""
            input_chat_id = st.text_input("📱 내 텔레그램 Chat ID", value=tele_chat_id)
            if input_chat_id != tele_chat_id and st.button("저장"):
                user_ref.update({'telegram_chat_id': input_chat_id}); st.success("저장 완료!"); time.sleep(1); st.rerun()
            tele_chat_id = input_chat_id

st.markdown("---")

def send_telegram_message(token, chat_id, text):
    try: return requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5).status_code == 200
    except: return False

def load_portfolio():
    if db:
        try: doc = db.collection('portfolios').document(st.session_state.user_id).get()
        except: doc = None
        if doc and doc.exists and 'stocks' in doc.to_dict(): return pd.DataFrame(doc.to_dict()['stocks'])
    return pd.read_csv(f'portfolio_data_{st.session_state.user_id}.csv') if os.path.exists(f'portfolio_data_{st.session_state.user_id}.csv') else pd.DataFrame(columns=['종목명', '매수단가', '수량'])

def save_portfolio(df):
    if db:
        try: db.collection('portfolios').document(st.session_state.user_id).set({'stocks': df.to_dict('records')}); return
        except: pass
    df.to_csv(f'portfolio_data_{st.session_state.user_id}.csv', index=False)

if 'portfolio' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.portfolio, st.session_state.current_user = load_portfolio(), st.session_state.user_id

@st.cache_data(ttl=86400)
def get_stock_info(query):
    query = str(query).strip().replace(" ", "").upper()
    if not query: return None, None
    if re.match(r'^[A-Z0-9\.]+$', query): return query, query
    try:
        df_krx = fdr.StockListing('KRX'); df_krx['Name_NoSpace'] = df_krx['Name'].str.replace(" ", "").str.upper()
        if query.isdigit() and len(query) == 6 and not df_krx[df_krx['Code'] == query].empty: return df_krx[df_krx['Code'] == query]['Name'].values[0], query
        match = df_krx[df_krx['Name_NoSpace'] == query]
        if not match.empty: return match['Name'].values[0], match['Code'].values[0]
        match_partial = df_krx[df_krx['Name_NoSpace'].str.contains(query, na=False)]
        if not match_partial.empty: best = match_partial.assign(NameLen=match_partial['Name'].str.len()).sort_values('NameLen').iloc[0]; return best['Name'], best['Code']
    except: pass
    top_stocks = {"삼성전자":"005930", "SK하이닉스":"000660", "현대차":"005380", "카카오":"035720", "NAVER":"035420", "알테오젠":"196170", "LG에너지솔루션":"373220"}
    for name, code in top_stocks.items():
        if query in name.replace(" ", ""): return name, code
    return None, None

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

# 💡 [업그레이드] 런 백테스트: 차트에 찍을 Buy/Sell 마커 기록 추가
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

# ==========================================
# 4. 메인 화면
# ==========================================
col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "알테오젠", "애플(AAPL)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (일부만 쳐도 검색됨 / 영문 코드)", "삼성전자")
    else: stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search; st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "💼 내 포트폴리오", "🔍 VIP 스크리너 (타점 분석)"])

# [탭 1] 차트 분석
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("❌ 종목을 찾을 수 없습니다."); st.stop()

    st.subheader(f"📊 {actual_name} 실시간 차트 & 타점 분석")
    with st.spinner("빅데이터 연산 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) # 백테스트 자동 실행
        except: df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) # 120일로 차트 표시 기간 약간 확대
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#8b5cf6', width=1.5), name='5일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#f59e0b', width=1.5), name='15일선'))
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#94a3b8', width=2, dash='dot'), name='200일선'))
        
        # 💡 [업그레이드] Buy / Sell 마커 차트에 추가
        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]; b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]; s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', color='red', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매수 타점'))
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', color='blue', size=14, line=dict(width=1, color='DarkSlateGrey')), name='매도 타점'))

        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=10, r=10, t=10, b=20), legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 타점 상세 안내 패널
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        curr_p = float(df['Close'].iloc[-1])
        entry2 = float(tech_ind['EMA15']) # 15일선 지지점
        tar_p = curr_p + (float(tech_ind['ATR']) * 4)
        stop_p = curr_p - (float(tech_ind['ATR']) * 2)
        
        # 현재가 기준 손익비
        rr_1 = (tar_p - curr_p) / (curr_p - stop_p) if (curr_p - stop_p) > 0 else 0
        # 2차 타점(눌림목) 기준 손익비
        rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0

        c1.markdown("🎯 **추천 매수 타점**")
        c1.info(f"**1차:** {int(curr_p):,}원 (돌파)\n\n**2차:** {int(entry2):,}원 (눌림)")
        
        c2.markdown("🛡️ **목표 및 손절 라인**")
        c2.warning(f"**목표가:** {int(tar_p):,}원\n\n**손절가:** {int(stop_p):,}원")
        
        c3.markdown("⚖️ **타점 매력도 (손익비)**")
        c3.success(f"**현재가 진입시:** {rr_1:.1f}배\n\n**2차 진입시:** {rr_2:.1f}배 (극대화)")

# [탭 3] VIP 검색기
with tab3:
    st.subheader("🔍 매수 급소 AI 스크리너")
    mode = st.radio("모드", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)"])
    send_to_telegram = st.checkbox("📱 스캔 완료 시 텔레그램 전송", value=True)
    
    if st.button("🔎 검색 실행", type="primary", use_container_width=True):
        with st.spinner("전체 시장 종목을 불러오는 중입니다..."):
            sl = {"삼성전자":"005930", "SK하이닉스":"000660", "LG에너지솔루션":"373220", "현대차":"005380", "기아":"000270"} if "한국 우량주" in mode else fdr.StockListing('KOSPI').head(200).set_index('Name')['Code'].to_dict()
            res = []; bar = st.progress(0); txt = st.empty()
            
            for i, (n, c) in enumerate(sl.items()):
                txt.text(f"스캔 중... {n} ({i+1}/{len(sl)})")
                try:
                    df, ind = calculate_cloud_indicators(fdr.DataReader(c, (datetime.today()-timedelta(days=300)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
                    if ind:
                        sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                        if sc >= 2 and ind.get("Is_Above_Monthly_EMA10") and ind['MACD_Cross'] and ((ind['RSI'] > 50) or (ind['RSI'] <= 35)):
                            p = float(df['Close'].iloc[-1]); a = float(ind['ATR'])
                            tar_p = p + (a*4); stop_p = p - (a*2); entry2 = float(ind['EMA15'])
                            rr_2 = (tar_p - entry2) / (entry2 - stop_p) if (entry2 - stop_p) > 0 else 0
                            
                            res.append({"종목명": n, "시그널": "🔥강력" if sc==4 else "👍분할", "현재가": p, "2차타점": entry2, "목표가": tar_p, "손절가": stop_p, "손익비_2차": rr_2})
                except: pass
                bar.progress((i+1)/len(sl))
            txt.text("✅ 스캔 완료!")
            
            if res:
                df_res = pd.DataFrame(res)
                st.dataframe(df_res, use_container_width=True, hide_index=True)
                
                # 💡 [업그레이드] 텔레그램 메시지에 1/2차 타점 및 손익비 추가
                if send_to_telegram and tele_token and tele_chat_id:
                    chunks = []; msg = f"🚀 <b>클라우드 퀀트 스캔 완료</b>\n\n"
                    for r in res:
                        info = f"<b>{r['종목명']}</b> ({r['시그널']})\n"
                        info += f" └ 🎯 <b>매수:</b> 1차 {int(r['현재가']):,}원 / 2차 {int(r['2차타점']):,}원\n"
                        info += f" └ 🎯 <b>목표:</b> {int(r['목표가']):,}원\n"
                        info += f" └ 🛡️ <b>손절:</b> {int(r['손절가']):,}원\n"
                        info += f" └ ⚖️ <b>손익비(2차 기준):</b> {r['손익비_2차']:.1f}배\n\n"
                        if len(msg) + len(info) > 3800: chunks.append(msg); msg = info
                        else: msg += info
                    chunks.append(msg)
                    for c in chunks: send_telegram_message(tele_token, tele_chat_id, c); time.sleep(0.3)
                    st.success("📱 텔레그램 전송 완료!")
            else: st.warning("조건에 맞는 매수 타점 종목이 없습니다.")
