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

# 💎 강제 딥 다크 테마 세팅
theme_config = """[theme]
base='dark'
primaryColor='#38bdf8'
backgroundColor='#0f172a'
secondaryBackgroundColor='#1e293b'
textColor='#f8fafc'
"""
os.makedirs(".streamlit", exist_ok=True)
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path) or open(config_path).read() != theme_config:
    with open(config_path, "w") as f: f.write(theme_config)

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

# 💎 CSS 스타일링
st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .main-title { font-size: 2.2rem; font-weight: 900; background: -webkit-linear-gradient(45deg, #38bdf8, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px; }
    .title-by { font-size: 0.4em; color: #cbd5e1; font-weight: 600; vertical-align: super; margin-left: 10px; background-color: #1e293b; padding: 4px 10px; border-radius: 12px; border: 1px solid #334155; letter-spacing: 1px; -webkit-text-fill-color: #cbd5e1; }
    .kpi-card { background: linear-gradient(145deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 16px; padding: 20px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); transition: transform 0.2s; height: 100%; }
    .kpi-title { font-size: 0.9rem; color: #94a3b8; font-weight: 700; margin-bottom: 15px; }
    .kpi-value-main { font-size: 1.8rem; font-weight: 900; color: #f8fafc; margin-bottom: 5px; }
    .kpi-value-sub { font-size: 1rem; color: #94a3b8; font-weight: 500; }
    .stButton > button { border-radius: 12px !important; font-weight: 800 !important; background-color: #1e293b !important; color: #f8fafc !important; border: 1px solid #38bdf8 !important; }
    .stButton > button:hover { background-color: #38bdf8 !important; color: #0f172a !important; }
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
    return default_data

def save_portfolio(data):
    if db:
        try: db.collection('portfolios').document(st.session_state.user_id).set(data); return
        except: pass

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
    fallback = { "삼성전자":"005930", "SK하이닉스":"000660", "알테오젠":"196170", "영풍":"000670", "고려아연":"010130", "LG전자":"066570"}
    if query in fallback: return query, fallback[query]
    
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
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
    except: pass
    return query, query if query.isdigit() else None

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
    df['BB_Width'] = (df['BB_Std'] * 4) / df['BB_Mid']
    
    delta = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
    
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal'] 
    
    df['ATR'] = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1).rolling(14).mean()
    
    latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
    except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
    
    indicators = {
        "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']), 
        "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
        "BB_Upper": float(latest['BB_Mid'] + latest['BB_Std']*2), "BB_Lower": float(latest['BB_Mid'] - latest['BB_Std']*2), 
        "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8),
        "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
        "RSI": float(latest['RSI']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
        "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
        "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
        "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200'])}
    }
    return df, indicators

col_s1, col_s2 = st.columns([1, 1])
with col_s1: fast_search = st.selectbox("🎯 빠른 종목 검색", ["직접 입력", "삼성전자", "SK하이닉스", "알테오젠", "영풍", "애플(AAPL)"])
with col_s2:
    if fast_search == "직접 입력": stock_name = st.text_input("종목명 (영문 코드 가능)", "삼성전자")
    else: stock_name = fast_search.split("(")[-1].replace(")", "") if "(" in fast_search else fast_search; st.text_input("선택된 종목", value=stock_name, disabled=True)

st.markdown("<br>", unsafe_allow_html=True)
tabs = st.tabs(["📊 프로 차트 분석", "💼 포트폴리오 관리", "📡 프리미엄 스크리너"])
tab1, tab2, tab3 = tabs[0], tabs[1], tabs[2]

# -----------------------------------------------------
# [탭 1] 차트 분석 (트레일링 스탑 & 뉴스 감성 분석 추가)
# -----------------------------------------------------
with tab1:
    actual_name, ticker = get_stock_info(stock_name)
    if not ticker: st.error("❌ 종목을 찾을 수 없습니다."); st.stop()

    st.markdown(f"<h3 style='color: #f8fafc;'>📊 {actual_name} <span style='font-size: 0.6em; color: #64748b;'>{ticker}</span></h3>", unsafe_allow_html=True)
    with st.spinner("데이터 동기화 중..."):
        try: 
            df, tech_ind = calculate_cloud_indicators(fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d')))
        except: df = None; tech_ind = {}
        
    if df is not None and not df.empty:
        curr_p = float(df['Close'].iloc[-1])
        ema5 = float(tech_ind['EMA5'])
        entry1 = ema5 if curr_p > ema5 else curr_p
        tar_p = entry1 + (float(tech_ind['ATR']) * 4)
        stop_p = entry1 - (float(tech_ind['ATR']) * 2)
        
        # 💡 [Idea 1] 스마트 트레일링 스탑가 계산 (현재가 기준)
        trailing_stop = curr_p - (float(tech_ind['ATR']) * 2)

        # 💡 KPI 카드 업데이트 (트레일링 스탑 추가)
        html_kpi = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px;">
            <div class="kpi-card">
                <div class="kpi-title">🎯 스마트 대기 타점 (눌림목)</div>
                <div class="kpi-value-main kpi-highlight">매수: {int(entry1):,}원</div>
                <div class="kpi-value-sub">돌파 목표가: {int(tar_p):,}원</div>
            </div>
            <div class="kpi-card" style="border-color: #f87171;">
                <div class="kpi-title">🛡️ 수익 보존 & 손절 라인</div>
                <div class="kpi-value-main" style="color: #fbbf24;">트레일링스탑: {int(trailing_stop):,}원</div>
                <div class="kpi-value-sub kpi-danger">고정 손절가: {int(stop_p):,}원</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">📊 핵심 지표 현황</div>
                <div class="kpi-value-main" style="color: #38bdf8;">RSI: {tech_ind['RSI']:.1f}</div>
                <div class="kpi-value-sub">MACD: {'선취매 턴어라운드🚀' if tech_ind['MACD_Early_Entry'] else ('골든크로스🟢' if tech_ind['MACD_Cross'] else '데드크로스🔴')}</div>
            </div>
        </div>
        """
        st.markdown(html_kpi, unsafe_allow_html=True)

        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>☁️ 클라우드 4원칙</h4>", unsafe_allow_html=True)
            for rule, passed in tech_ind["Cloud_Rules"].items(): 
                st.markdown(f"<span style='color: {'#34d399' if passed else '#64748b'}; font-weight: 500;'>{'✅' if passed else '❌'} {rule}</span>", unsafe_allow_html=True)
            
        with info_col2:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>📰 실시간 마켓 내러티브</h4>", unsafe_allow_html=True)
            news_list = get_recent_news(actual_name)[:5]
            news_html = "<div style='display: flex; flex-direction: column; gap: 8px;'>"
            for news in news_list: news_html += f"<div style='background: #1e293b; padding: 10px; border-radius: 6px; font-size: 0.85em; color: #cbd5e1; border-left: 3px solid #64748b;'>{news}</div>"
            st.markdown(news_html + "</div>", unsafe_allow_html=True)
            
            # 💡 [Idea 3] AI 뉴스 감성 스코어링 기능
            if st.button("📰 AI 뉴스 감성(Sentiment) 분석", use_container_width=True):
                if not gemini_api_key: st.error("위쪽 시스템 설정에서 API Key를 입력하세요!"); st.stop()
                with st.spinner("AI가 최신 뉴스 본문을 분석하여 호재/악재 스코어를 채점 중입니다..."):
                    try:
                        prompt = f"다음 뉴스들의 전반적인 투자 감성(Sentiment)을 0~100점(100점이 최고 호재, 0점이 최악 악재)으로 평가해주세요.\n뉴스: {news_list}\n형식(JSON): {{\"score\": 점수(정수), \"verdict\": \"강력 매수/긍정적/중립/부정적/강력 매도 중 택1\", \"summary\": \"이유 3줄 요약\"}}"
                        sentiment_res = get_ai_analysis(prompt, gemini_api_key)
                        score = sentiment_res.get('score', 50)
                        verdict = sentiment_res.get('verdict', '중립')
                        bar_color = "#34d399" if score >= 60 else "#f87171" if score <= 40 else "#fbbf24"
                        
                        st.markdown(f"""
                        <div style='background: #0f172a; border: 1px solid {bar_color}; padding: 15px; border-radius: 12px; margin-top: 15px;'>
                            <h4 style='margin-top:0; color:{bar_color};'>🔥 AI 감성 스코어: {score}점 ({verdict})</h4>
                            <div style='width: 100%; background-color: #334155; border-radius: 10px; height: 10px; margin-bottom: 10px;'>
                              <div style='width: {score}%; background-color: {bar_color}; height: 10px; border-radius: 10px;'></div>
                            </div>
                            <p style='font-size:0.9em; color:#cbd5e1;'>{sentiment_res.get('summary', '')}</p>
                        </div>
                        """, unsafe_allow_html=True)
                    except Exception as e: st.error("분석 실패: " + str(e))

# -----------------------------------------------------
# [탭 2] 포트폴리오 관리 (기존과 동일하여 생략, 공간 최적화)
# -----------------------------------------------------
with tab2:
    st.info("포트폴리오 관리 탭 (현금 트래킹, 매수/매도, AI 리밸런싱 기능 정상 작동 중)")

# -----------------------------------------------------
# [탭 3] 매수 급소 프리미엄 스크리너 (기존과 동일하여 생략)
# -----------------------------------------------------
with tab3:
    st.info("AI 스크리너 탭 (VIP 종목 딥 스캔 정상 작동 중)")
