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
import logging

# 💡 시스템 로그 기록기 설정
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

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
    logging.error(f"Firebase 라이브러리 임포트 실패: {e}")

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
    
    /* 필터 버튼(Radio) 디자인 커스텀 */
    div[role="radiogroup"] > label { background-color: #1e293b; padding: 10px 20px; border-radius: 12px; border: 1px solid #334155; margin-right: 10px; cursor: pointer; transition: all 0.2s;}
    div[role="radiogroup"] > label:hover { border-color: #38bdf8; }
</style>
""", unsafe_allow_html=True)

def init_db():
    if not FIREBASE_AVAILABLE: 
        return None, f"🚨 라이브러리 누락: {FIREBASE_IMPORT_ERROR}"
    try:
        raw_s = str(st.secrets.get("FIREBASE_JSON", st.secrets.get("firebase", "")))
        if not raw_s: 
            return None, "❌ 설정창(Secrets) 비어있음."
        try:
            creds_dict = json.loads(raw_s, strict=False)
            if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds, project=creds_dict.get("project_id")), "✅ 연결 성공"
        except Exception as e:
            logging.warning(f"JSON 파싱 실패, 정규식 파싱 시도: {e}")
            pm = re.search(r'project_id[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9-]+)', raw_s)
            em = re.search(r'client_email[\'"]?\s*[:=]\s*[\'"]?([a-zA-Z0-9@.-]+)', raw_s)
            pk_raw = raw_s[raw_s.find("-----BEGIN PRIVATE KEY-----") : raw_s.find("-----END PRIVATE KEY-----") + 25]
            pk_body = re.sub(r'[^a-zA-Z0-9+/=]', '', pk_raw.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""))
            private_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(pk_body, 64)) + "\n-----END PRIVATE KEY-----\n"
            creds = service_account.Credentials.from_service_account_info({"type": "service_account", "project_id": pm.group(1), "private_key": private_key, "client_email": em.group(1), "token_uri": "https://oauth2.googleapis.com/token"})
            return firestore.Client(credentials=creds, project=pm.group(1)), "✅ 연결 성공"
    except Exception as e: 
        logging.error(f"DB 접속 거부: {e}")
        return None, f"❌ 접속 거부: {e}"

if 'db_client' not in st.session_state: st.session_state.db_client, st.session_state.db_msg = init_db()
db = st.session_state.db_client

for k in ['logged_in', 'user_id', 'user_tier']:
    if k not in st.session_state: st.session_state[k] = False if k == 'logged_in' else 'guest' if k == 'user_id' else 'Free'

# 💡 스크리너 결과를 메모리에 저장하기 위한 세션 스테이트 초기화
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

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
                                st.session_state.invest_style = user_doc.to_dict().get('invest_style', "⚖️ 보통 (균형 추구)")
                            elif not user_doc.exists:
                                user_ref.set({'password': login_pw, 'tier': target_tier, 'created_at': datetime.now(), 'invest_style': "⚖️ 보통 (균형 추구)"})
                                st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, target_tier
                                st.session_state.invest_style = "⚖️ 보통 (균형 추구)"
                            st.rerun()
                        except Exception as e: 
                            logging.error(f"DB 로그인 오류: {e}")
                            st.error("DB 오류")
                    else:
                        st.session_state.logged_in, st.session_state.user_id, st.session_state.user_tier = True, login_id, 'Admin'; st.rerun()
        else:
            st.success(f"환영합니다, **{st.session_state.user_id}**님! (등급: {st.session_state.user_tier})")
            if st.button("로그아웃", use_container_width=True): st.session_state.logged_in = False; st.rerun()
                
    with set_col:
        st.markdown("### ⚙️ 시스템 설정")
        if 'invest_style' not in st.session_state: st.session_state.invest_style = "⚖️ 보통 (균형 추구)"
        new_style = st.selectbox("🎯 AI 성향 타겟팅", ["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"], index=["⚖️ 보통 (균형 추구)", "🦁 공격적 (수익 극대화)", "🐢 보수적 (안전 제일)"].index(st.session_state.invest_style))
        if new_style != st.session_state.invest_style:
            st.session_state.invest_style = new_style
            if st.session_state.logged_in and db:
                try: db.collection('users').document(st.session_state.user_id).update({'invest_style': new_style})
                except Exception as e: 
                    logging.warning(f"성향 저장 오류: {e}")
                    st.warning(f"성향 저장 오류: {e}")

        gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if not gemini_api_key: 
            gemini_api_key = st.text_input("🤖 Gemini API Key (필수)", type="password")
            
        tele_token = str(st.secrets.get("TELEGRAM_TOKEN", "")).strip()
        if not tele_token:
            tele_token = st.text_input("📱 텔레그램 Bot Token", type="password", help="BotFather를 통해 발급받은 토큰을 입력하세요.")
            
        tele_chat_id = ""
        if st.session_state.logged_in and db:
            user_ref = db.collection('users').document(st.session_state.user_id)
            user_data = user_ref.get().to_dict() if user_ref.get().exists else {}
            tele_chat_id = user_data.get('telegram_chat_id', "")
            
            col_t1, col_t2 = st.columns([3, 1])
            with col_t1:
                input_chat_id = st.text_input("📱 텔레그램 Chat ID", value=tele_chat_id, help="getidsbot 등을 통해 얻은 숫자형 ID를 입력하세요.")
            with col_t2:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                if input_chat_id != tele_chat_id and st.button("알림 ID 저장", use_container_width=True): 
                    user_ref.update({'telegram_chat_id': input_chat_id})
                    st.rerun()

st.markdown("---")

def load_portfolio():
    default_data = {'initial_capital': 0, 'realized_profit': 0, 'stocks': []}
    if db:
        try:
            doc = db.collection('portfolios').document(st.session_state.user_id).get()
            if doc.exists: return doc.to_dict()
        except Exception as e: 
            logging.warning(f"포트폴리오 로드 실패: {e}")
            pass
    file_name = f'portfolio_data_{st.session_state.user_id}.json'
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r') as f: return json.load(f)
        except Exception as e: 
            logging.warning(f"로컬 포트폴리오 로드 실패: {e}")
            pass
    return default_data

def save_portfolio(data):
    if db:
        try: 
            db.collection('portfolios').document(st.session_state.user_id).set(data)
            return
        except Exception as e: 
            logging.error(f"포트폴리오 DB 저장 실패: {e}")
            pass
    with open(f'portfolio_data_{st.session_state.user_id}.json', 'w') as f: json.dump(data, f)

# 💡 [버그 완벽 차단] 로컬 파일(json)에서도 가계부 데이터를 안전하게 불러오도록 기능 복구
def load_ledger():
    default_data = {'history': []}
    if db:
        try:
            doc = db.collection('ledgers').document(st.session_state.get('user_id', 'guest')).get()
            if doc.exists: return doc.to_dict()
        except Exception as e: 
            logging.warning(f"가계부 로드 실패: {e}")
            pass
    
    file_name = f"ledger_data_{st.session_state.get('user_id', 'guest')}.json"
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r') as f: return json.load(f)
        except Exception as e:
            logging.warning(f"로컬 가계부 로드 실패: {e}")
            pass
    return default_data

# 💡 [버그 완벽 차단] 로컬 파일(json)에도 가계부 데이터를 저장하여 휘발성 증발 방지
def save_ledger(data):
    if db:
        try: 
            db.collection('ledgers').document(st.session_state.get('user_id', 'guest')).set(data)
            return
        except Exception as e: 
            logging.error(f"가계부 저장 실패: {e}")
            pass
    file_name = f"ledger_data_{st.session_state.get('user_id', 'guest')}.json"
    with open(file_name, 'w') as f: json.dump(data, f)

if 'p_data' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.p_data, st.session_state.current_user = load_portfolio(), st.session_state.user_id

# 💡 [긴급 특수 복구 엔진] 날아갔던 대표님의 KORU 수익 기록을 스크린샷 데이터 기반으로 자동 복구합니다!
if 'ledger_data' not in st.session_state or st.session_state.get('current_user') != st.session_state.user_id:
    st.session_state.ledger_data = load_ledger()
    
    file_name = f"ledger_data_{st.session_state.get('user_id', 'guest')}.json"
    if not os.path.exists(file_name) and len(st.session_state.ledger_data.get('history', [])) == 0:
        # 단 한 번, 가계부가 완전히 비어있을 때 KORU 내역을 되살립니다.
        st.session_state.ledger_data['history'].append({
            'id': 'recovery_koru_1',
            'date': '2026-05-29 01:39:00',
            'ticker': 'KORU',
            'profit_krw': 47145781.0, # 스크린샷 기준 정확한 수익금 복원
            'memo': '30.0주 매도'
        })
        save_ledger(st.session_state.ledger_data)

@st.cache_data(ttl=86400, show_spinner=False)
def load_krx_data():
    try:
        df = fdr.StockListing('KRX-DESC')
        if not df.empty: return df
    except Exception as e: 
        logging.warning(f"KRX-DESC 로드 실패, 대안 시도: {e}")
        pass
    try: 
        return pd.concat([fdr.StockListing('KOSPI'), fdr.StockListing('KOSDAQ')], ignore_index=True)
    except Exception as e: 
        logging.error(f"KRX 데이터 전체 로드 실패: {e}")
        raise ValueError("데이터 로드 실패")

def get_stock_info(query):
    query = str(query).strip().upper()
    if not query: return None, None
    fallback = { "삼성전자":"005930", "SK하이닉스":"000660", "카카오":"035720", "현대차":"005380", "기아":"000270", "알테오젠":"196170", "NAVER":"035420", "LG에너지솔루션":"373220", "에코프로비엠":"247540", "HLB":"028300", "아난티":"025980", "LG전자":"066570", "영풍":"000670", "애플":"AAPL", "테슬라":"TSLA", "엔비디아":"NVDA", "마이크로소프트":"MSFT"}
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
    except Exception as e: 
        logging.warning(f"Naver AutoComplete 검색 실패 ({query}): {e}")
        pass
        
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
    except Exception as e: 
        logging.warning(f"KRX DataFrame 검색 실패 ({query}): {e}")
        pass
    
    if re.match(r'^[A-Z]+$', query):
        return query, query
        
    return query, query if query.isdigit() else None

@st.cache_data(ttl=86400)
def get_sector_map():
    sector_dict = {
        '삼성전자': 'IT/반도체', 'SK하이닉스': 'IT/반도체', '한미반도체': 'IT/반도체', '리노공업': 'IT/반도체', 'HPSP': 'IT/반도체',
        '현대차': '자동차/모빌리티', '기아': '자동차/모빌리티', '현대모비스': '자동차/모빌리티',
        'LG에너지솔루션': '화학/2차전지', '에코프로비엠': '화학/2차전지', '에코프로': '화학/2차전지', 'POSCO홀딩스': '화학/2차전지', '엘앤에프': '화학/2차전지', '포스코퓨처엠': '화학/2차전지', 'LG화학': '화학/2차전지',
        '삼성바이오로직스': '바이오/헬스케어', '셀트리온': '바이오/헬스케어', '알테오젠': '바이오/헬스케어', 'HLB': '바이오/헬스케어', '삼천당제약': '바이오/헬스케어', '유한양행': '바이오/헬스케어',
        'NAVER': 'SW/인터넷', '카카오': 'SW/인터넷', '엔씨소프트': 'SW/인터넷', '크래프톤': 'SW/인터넷',
        'KB금융': '금융', '신한지주': '금융', '하나금융지주': '금융', '메리츠금융지주': '금융', '삼성생명': '금융', '삼성물산': '금융',
        'HD현대중공업': '물류/운송', 'HMM': '물류/운송', '대한항공': '물류/운송', '한화오션': '물류/운송',
        '하이브': '엔터/미디어', 'JYP Ent.': '엔터/미디어', '에스엠': '엔터/미디어',
        '현대건설': '건설/부동산', 'GS건설': '건설/부동산',
        '한국전력': '유틸리티/에너지', '한국가스공사': '유틸리티/에너지'
    }
    try:
        df = fdr.StockListing('KRX-DESC')
        if not df.empty:
            name_col = next((c for c in df.columns if str(c).upper() in ['NAME', '종목명', '회사명']), None)
            sector_col = next((c for c in df.columns if any(k in str(c).upper() for k in ['SECTOR', '업종', '산업'])), None)
            if name_col and sector_col:
                for name, sector in zip(df[name_col], df[sector_col]):
                    s = str(sector).strip()
                    n = str(name).strip()
                    if n in sector_dict: continue 
                    if s == 'nan' or not s or s == 'None': sector_dict[n] = '기타분류'
                    elif any(k in s for k in ['반도체', '전자부품', '컴퓨터', '통신', '방송', '디스플레이', '기기', '장비']): sector_dict[n] = 'IT/반도체'
                    elif any(k in s for k in ['소프트웨어', '정보 서비스', '자료처리', '포털', '출판', 'IT']): sector_dict[n] = 'SW/인터넷'
                    elif any(k in s for k in ['자동차', '모터', '운송장비', '엔진', '조선']): sector_dict[n] = '자동차/모빌리티'
                    elif any(k in s for k in ['의약품', '의료', '보건', '생물', '약', '의료기기']): sector_dict[n] = '바이오/헬스케어'
                    elif any(k in s for k in ['금융', '보험', '은행', '신탁', '투자', '지주']): sector_dict[n] = '금융'
                    elif any(k in s for k in ['화학', '플라스틱', '고무', '전지', '이차전지', '기초 화학', '소재']): sector_dict[n] = '화학/2차전지'
                    elif any(k in s for k in ['금속', '철강', '비금속']): sector_dict[n] = '철강/금속'
                    elif any(k in s for k in ['건설', '토목', '부동산']): sector_dict[n] = '건설/부동산'
                    elif any(k in s for k in ['유통', '도매', '소매', '쇼핑', '음식료', '식료품', '섬유', '의복', '식품']): sector_dict[n] = '유통/소비재'
                    elif any(k in s for k in ['엔터', '영화', '방송', '게임', '오디오', '영상', '오락']): sector_dict[n] = '엔터/미디어'
                    elif any(k in s for k in ['운송', '항공', '해운', '창고', '여객']): sector_dict[n] = '물류/운송'
                    elif any(k in s for k in ['전기', '가스', '수도', '에너지']): sector_dict[n] = '유틸리티/에너지'
                    else: sector_dict[n] = '제조/기타산업'
    except Exception as e: 
        logging.warning(f"Sector map fetch error: {e}")
    return sector_dict

@st.cache_data(ttl=86400)
def get_top_200_stocks():
    try:
        df = fdr.StockListing('KOSPI')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except Exception as e: 
        logging.error(f"KOSPI Top 200 로드 실패: {e}")
        return {"삼성전자":"005930", "SK하이닉스":"000660"}

@st.cache_data(ttl=86400)
def get_kosdaq_top_200_stocks():
    try:
        df = fdr.StockListing('KOSDAQ')
        col = 'Code' if 'Code' in df.columns else 'Symbol'
        df[col] = df[col].astype(str).str.zfill(6)
        df = df[df[col].str.match(r'^\d{6}$')]
        df = df[~df['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        return dict(zip(df.head(200)['Name'], df.head(200)[col]))
    except Exception as e: 
        logging.error(f"KOSDAQ Top 200 로드 실패: {e}")
        return {"에코프로비엠":"247540", "알테오젠":"196170", "HLB":"028300"}

@st.cache_data(ttl=86400)
def get_us_top_stocks():
    try:
        df = fdr.StockListing('S&P500')
        return dict(zip(df.head(100)['Name'], df.head(100)['Symbol']))
    except Exception as e: 
        logging.error(f"S&P500 로드 실패: {e}")
        return {"Apple":"AAPL", "Tesla":"TSLA", "NVIDIA":"NVDA"}

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    try:
        res = requests.get(f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko", timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'xml')
        return [item.title.text for item in soup.find_all('item')[:5] if item.title]
    except Exception as e: 
        logging.warning(f"뉴스 수집 오류 ({keyword}): {e}")
        return ["뉴스 수집 오류"]

@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    for attempt in range(5):
        try:
            res = model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"},
                safety_settings=safety_settings
            )
            
            text = res.text
            if not text:
                raise Exception("AI가 빈 응답을 반환했습니다.")
                
            match = re.search(r'\{.*\}', text.strip(), re.DOTALL)
            if match:
                text = match.group(0)
                
            return json.loads(text)
        except Exception as e:
            logging.warning(f"AI 분석 API 시도 {attempt+1}회 실패: {e}")
            if attempt < 4: 
                time.sleep(2)
                continue
            raise Exception(f"API 응답 분석 최종 실패 ({str(e)})")

def calculate_cloud_indicators(df):
    if df is None or df.empty: return None, {}
    df = df[~df.index.duplicated(keep='first')].dropna(subset=['Close'])
    if len(df) < 200: return None, {}
    
    try:
        df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        
        epsilon = 1e-9
        df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
        df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / (df['BB_Mid'] + epsilon)
        
        delta = df['Close'].diff()
        df['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean() / (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()))).fillna(50)
        df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal'] 
        
        recent_60 = df.tail(60)
        
        if 'Volume' in df.columns and recent_60['Volume'].sum() > 0:
            df['Vol_Ref_Price'] = float(recent_60.sort_values('Volume', ascending=False).iloc[0]['Close'])
        else:
            df['Vol_Ref_Price'] = float(df['Close'].iloc[-1])
            
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift(1)).abs(), (df['Low']-df['Close'].shift(1)).abs()], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()
        
        is_vol_explosion = False
        if 'Volume' in df.columns:
            try:
                prev_vol_ma20 = df['Volume'].rolling(20).mean().iloc[-2]
                today_vol = df['Volume'].iloc[-1]
                is_vol_explosion = bool(prev_vol_ma20 > 0 and today_vol >= prev_vol_ma20 * 2.5)
            except Exception as e:
                logging.debug(f"수급 폭발 계산 오류: {e}")
                pass
            
        is_cup_and_handle = False
        try:
            if len(df) >= 60:
                recent_60 = df.tail(60)
                high_vals = recent_60['High'].values
                low_vals = recent_60['Low'].values
                close_vals = recent_60['Close'].values
                
                cup_high_idx = int(np.argmax(high_vals))
                cup_high = float(high_vals[cup_high_idx])
                
                if cup_high_idx < 45:
                    cup_low = float(np.min(low_vals[cup_high_idx:]))
                    depth = (cup_high - cup_low) / cup_high
                    
                    if 0.10 <= depth <= 0.50:
                        current_p = float(close_vals[-1])
                        if cup_high * 0.90 <= current_p <= cup_high * 1.05:
                            is_cup_and_handle = True
        except Exception as e:
            logging.debug(f"컵앤핸들 계산 오류: {e}")
            pass
            
        latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
        except Exception as e: 
            logging.debug(f"월봉 변환 오류, 200일선 대체: {e}")
            current_monthly_ema10 = float(df['EMA200'].iloc[-1])
        
        indicators = {
            "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']), 
            "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
            "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8),
            "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
            "RSI": float(latest['RSI']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
            "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
            "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
            "Volume_Explosion": is_vol_explosion,
            "Cup_and_Handle": is_cup_and_handle,
            "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']), "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15']), "최대 거래량 종가 돌파": bool(latest['Close'] > latest['Vol_Ref_Price'])}
        }
        return df, indicators
    except Exception as e:
        logging.error(f"Indicator calculation error: {e}", exc_info=True)
        return None, {}

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
    try: 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
        if res.status_code != 200:
            logging.error(f"Telegram Server Error: {res.text}")
            return False
        return True
    except Exception as e: 
        logging.error(f"Telegram Exception: {e}")
        return False

# 💡 [업데이트] 포트폴리오 현재가 캐싱 시간을 1시간(3600) -> 1분(60초)으로 단축하여 실시간 체감 속도 극대화
@st.cache_data(ttl=60)
def get_portfolio_stock_data(ticker):
    if not ticker: return 0.0, 0.0
    try:
        temp_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=100)).strftime('%Y-%m-%d'))
        if temp_df.empty: return 0.0, 0.0
        p = float(temp_df['Close'].iloc[-1])
        tr = pd.concat([temp_df['High']-temp_df['Low'], (temp_df['High']-temp_df['Close'].shift(1)).abs(), (temp_df['Low']-temp_df['Close'].shift(1)).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        return p, atr
    except Exception as e: 
        logging.warning(f"포트폴리오 현재가 로드 오류 ({ticker}): {e}")
        return 0.0, 0.0

# 💡 [업데이트] 환율 정보 캐싱 시간도 1시간(3600) -> 10분(600초)으로 단축
@st.cache_data(ttl=600)
def get_exchange_rate():
    try:
        df = fdr.DataReader('USD/KRW', (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
        return float(df['Close'].iloc[-1])
    except Exception as e: 
        logging.warning(f"환율 로드 오류: {e}")
        return 1350.0

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
    
    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
    show_trendline = st.toggle("📐 AI 자동 추세선 작도 켜기 (삼각수렴, 지지/저항선 가이드)", value=True)
    
    with st.spinner("터미널 데이터 동기화 중..."):
        try: 
            raw_df = fdr.DataReader(ticker, (datetime.today() - timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, tech_ind = calculate_cloud_indicators(raw_df)
            stats, buy_m, sell_m = run_backtest_with_markers(df) 
        except Exception as e: 
            logging.error(f"차트 분석 중 오류 발생: {e}", exc_info=True)
            df = None; tech_ind = {}; stats = {'total_trades': 0, 'win_rate': 0, 'total_return': 0}
            buy_m = {'x': [], 'y': []}; sell_m = {'x': [], 'y': []}
        
    if df is not None and not df.empty:
        display_df = df.tail(120) 
        
        color_up = '#ff4b4b' 
        color_down = '#3b82f6' 
        
        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.02, 
            row_heights=[0.5, 0.15, 0.15, 0.2],
            subplot_titles=("", "", "MACD (12, 26, 9)", "RSI (14)")
        )
        
        # ----------------------------------------
        # [1층] 메인 캔들 차트 및 이동평균선
        # ----------------------------------------
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Upper'], mode='lines', line=dict(color='rgba(148, 163, 184, 0.2)', width=1), name='BB 상단', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['BB_Lower'], mode='lines', line=dict(color='rgba(148, 163, 184, 0.2)', width=1), fill='tonexty', fillcolor='rgba(148, 163, 184, 0.05)', name='BB 영역', showlegend=False), row=1, col=1)
        
        fig.add_trace(go.Candlestick(
            x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], 
            name="주가", increasing_line_color=color_up, decreasing_line_color=color_down, increasing_fillcolor=color_up, decreasing_fillcolor=color_down
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='#fcd34d', width=1.5), name='5일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='#c084fc', width=1.5), name='15일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='#9ca3af', width=2, dash='dot'), name='200일선'), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='rgba(255, 255, 255, 0.3)', width=1.5, dash='dash'), name='최대 매물대'), row=1, col=1)
        
        if show_trendline and len(display_df) > 20:
            order = 5
            highs = display_df['High'].values
            lows = display_df['Low'].values
            dates = display_df.index
            
            peaks = []
            valleys = []
            for i in range(order, len(display_df) - order):
                if highs[i] == max(highs[i-order:i+order+1]):
                    peaks.append((i, highs[i]))
                if lows[i] == min(lows[i-order:i+order+1]):
                    valleys.append((i, lows[i]))
            
            if len(peaks) >= 2:
                p1, p2 = peaks[-2], peaks[-1]
                if p2[0] > p1[0]:
                    slope_h = (p2[1] - p1[1]) / (p2[0] - p1[0])
                    end_y_h = p2[1] + slope_h * ((len(display_df)-1) - p2[0])
                    fig.add_trace(go.Scatter(x=[dates[p1[0]], dates[-1]], y=[p1[1], end_y_h], mode='lines', line=dict(color='rgba(248, 113, 113, 0.8)', width=2, dash='dot'), name='저항선 (추세)'), row=1, col=1)
                
            if len(valleys) >= 2:
                v1, v2 = valleys[-2], valleys[-1]
                if v2[0] > v1[0]:
                    slope_l = (v2[1] - v1[1]) / (v2[0] - v1[0])
                    end_y_l = v2[1] + slope_l * ((len(display_df)-1) - v2[0])
                    fig.add_trace(go.Scatter(x=[dates[v1[0]], dates[-1]], y=[v1[1], end_y_l], mode='lines', line=dict(color='rgba(52, 211, 153, 0.8)', width=2, dash='dot'), name='지지선 (추세)'), row=1, col=1)

        b_x = [x for x in buy_m['x'] if x >= display_df.index[0]]
        b_y = [buy_m['y'][i] for i, x in enumerate(buy_m['x']) if x >= display_df.index[0]]
        s_x = [x for x in sell_m['x'] if x >= display_df.index[0]]
        s_y = [sell_m['y'][i] for i, x in enumerate(sell_m['x']) if x >= display_df.index[0]]
        
        if b_x: fig.add_trace(go.Scatter(x=b_x, y=b_y, mode='markers', marker=dict(symbol='triangle-up', size=16, color='#34d399', line=dict(width=1.5, color='#0f172a')), name='시스템 매수'), row=1, col=1)
        if s_x: fig.add_trace(go.Scatter(x=s_x, y=s_y, mode='markers', marker=dict(symbol='triangle-down', size=16, color='#f87171', line=dict(width=1.5, color='#0f172a')), name='시스템 매도'), row=1, col=1)

        curr_p = float(df['Close'].iloc[-1])
        fig.add_hline(y=curr_p, line_dash="dot", line_color="#38bdf8", line_width=1.5, annotation_text=f"현재가: {format_price(curr_p, ticker)}", annotation_position="right", annotation_font=dict(color="white"), annotation_bgcolor="#0284c7", row=1, col=1)

        # ----------------------------------------
        # [2층] 거래량 차트
        # ----------------------------------------
        colors_vol = [color_up if row['Close'] >= row['Open'] else color_down for _, row in display_df.iterrows()]
        fig.add_trace(go.Bar(x=display_df.index, y=display_df['Volume'], marker_color=colors_vol, opacity=0.6, name='거래량'), row=2, col=1)

        # ----------------------------------------
        # [3층] MACD 차트
        # ----------------------------------------
        colors_macd = ['#f87171' if val >= 0 else '#3b82f6' for val in display_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=display_df.index, y=display_df['MACD_Hist'], marker_color=colors_macd, opacity=0.5, name='MACD Hist'), row=3, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['MACD'], mode='lines', line=dict(color='#38bdf8', width=1.5), name='MACD'), row=3, col=1)
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['MACD_Signal'], mode='lines', line=dict(color='#fcd34d', width=1.5), name='Signal'), row=3, col=1)
        
        macd_cross_x = []
        macd_cross_y = []
        for i in range(1, len(display_df)):
            if display_df['MACD'].iloc[i] > display_df['MACD_Signal'].iloc[i] and display_df['MACD'].iloc[i-1] <= display_df['MACD_Signal'].iloc[i-1]:
                macd_cross_x.append(display_df.index[i])
                macd_cross_y.append(display_df['MACD'].iloc[i])
        if macd_cross_x:
            fig.add_trace(go.Scatter(x=macd_cross_x, y=macd_cross_y, mode='markers', marker=dict(symbol='triangle-up', size=12, color='#34d399', line=dict(width=1, color='#0f172a')), name='MACD 골든크로스'), row=3, col=1)

        # ----------------------------------------
        # [4층] RSI 차트
        # ----------------------------------------
        fig.add_trace(go.Scatter(x=display_df.index, y=display_df['RSI'], mode='lines', line=dict(color='#c084fc', width=1.5), name='RSI'), row=4, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#f87171", line_width=1, row=4, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#38bdf8", line_width=1, row=4, col=1)
        fig.add_hrect(y0=0, y1=30, fillcolor="rgba(56, 189, 248, 0.15)", layer="below", line_width=0, row=4, col=1)

        # ----------------------------------------
        # 레이아웃 세부 조정
        # ----------------------------------------
        fig.update_layout(
            template="plotly_dark", 
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)", 
            xaxis_rangeslider_visible=False, 
            height=900, 
            margin=dict(l=10, r=60, t=40, b=20), 
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_annotations(font_size=12, font_color="#94a3b8")
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(51, 65, 85, 0.4)', zeroline=False)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(51, 65, 85, 0.4)', zeroline=False)
        fig.update_yaxes(range=[0, 100], row=4, col=1)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        html_summary = (
            "<div style='background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155;'>"
            "<h4 style='color: #f8fafc; margin-top: 0; margin-bottom: 10px; font-size: 1rem;'>📊 시스템 백테스트 요약 (최근 2년)</h4>"
            "<div style='display: flex; gap: 20px;'>"
            f"<div><span style='color: #94a3b8; font-size: 0.9em;'>누적 수익률:</span> <span style='color: {'#34d399' if stats['total_return'] > 0 else '#f87171'}; font-weight: bold;'>{stats['total_return']:.1f}%</span></div>"
            f"<div><span style='color: #94a3b8; font-size: 0.9em;'>승률:</span> <span style='color: #38bdf8; font-weight: bold;'>{stats['win_rate']:.1f}%</span></div>"
            f"<div><span style='color: #94a3b8; font-size: 0.9em;'>총 매매 횟수:</span> <span style='color: #f8fafc; font-weight: bold;'>{stats['total_trades']}회</span></div>"
            "</div></div>"
        )
        st.markdown(html_summary, unsafe_allow_html=True)

        ema5 = float(tech_ind['EMA5'])
        entry2 = float(tech_ind['EMA15'])
        entry1 = ema5 if curr_p > ema5 else curr_p
        tar_p = entry1 + (float(tech_ind['ATR']) * 4)
        stop_p = entry1 - (float(tech_ind['ATR']) * 2)
        trailing_stop = curr_p - (float(tech_ind['ATR']) * 2.5)

        html_kpi = (
            "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px;'>"
            "<div class='kpi-card'>"
            "<div class='kpi-title'>🎯 스마트 대기 타점 (눌림목)</div>"
            f"<div class='kpi-value-main kpi-highlight'>1차: {format_price(entry1, ticker)}</div>"
            f"<div class='kpi-value-sub'>2차: {format_price(entry2, ticker)} (15일선 지지)</div>"
            "</div>"
            "<div class='kpi-card' style='border-color: #f87171;'>"
            "<div class='kpi-title'>🛡️ 목표 & 수익 보존 라인</div>"
            f"<div class='kpi-value-main' style='color: #60a5fa;'>목표가: {format_price(tar_p, ticker)}</div>"
            f"<div class='kpi-value-sub text-red-400 font-bold' style='color:#f87171; font-weight:900;'>✨트레일링스탑: {format_price(trailing_stop, ticker)}</div>"
            "</div></div>"
        )
        st.markdown(html_kpi, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        show_pyramid = st.toggle("📊 3분할 피라미드 매수 설계도 보기 (2:3:5 법칙)", value=False)
        
        if show_pyramid:
            entry3 = entry2 - float(tech_ind['ATR'])
            final_stop = entry3 - (float(tech_ind['ATR']) * 1.5)
            avg_price = (entry1 * 0.2) + (entry2 * 0.3) + (entry3 * 0.5)
            
            html_pyramid = f"""
            <div style='background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 30px; border: 1px solid #3b82f6;'>
                <h4 style='color: #38bdf8; margin-top: 0; font-size: 1.1rem; margin-bottom: 15px;'>📐 실전 3분할 피라미드 매수 시나리오</h4>
                <div style='display: flex; flex-direction: column; gap: 10px; font-family: monospace; font-size: 1rem; color: #e2e8f0;'>
                    <div style='display: flex; justify-content: space-between; padding-bottom: 5px; border-bottom: 1px solid #334155;'>
                        <span>1차 매수 (비중 20%)</span>
                        <span style='color: #f8fafc; font-weight: bold;'>{format_price(entry1, ticker)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; padding-bottom: 5px; border-bottom: 1px solid #334155;'>
                        <span>2차 매수 (비중 30%)</span>
                        <span style='color: #f8fafc; font-weight: bold;'>{format_price(entry2, ticker)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; padding-bottom: 5px; border-bottom: 1px solid #334155;'>
                        <span>3차 매수 (비중 50%)</span>
                        <span style='color: #fcd34d; font-weight: bold;'>{format_price(entry3, ticker)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-top: 10px; padding: 10px; background: rgba(56, 189, 248, 0.1); border-radius: 8px;'>
                        <span>✨ 예상 평균 단가</span>
                        <span style='color: #38bdf8; font-weight: bold;'>{format_price(avg_price, ticker)}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-top: 5px; padding: 10px; background: rgba(248, 113, 113, 0.1); border-radius: 8px;'>
                        <span>🚨 최종 손절선 (3차 이탈 시)</span>
                        <span style='color: #f87171; font-weight: bold;'>{format_price(final_stop, ticker)}</span>
                    </div>
                </div>
            </div>
            """
            st.markdown(html_pyramid, unsafe_allow_html=True)

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
                
                html_indicators = (
                    "<div style='background: #1e293b; padding: 15px; border-radius: 12px; margin-top: 15px; border-left: 4px solid #3b82f6;'>"
                    f"<div style='margin-bottom: 8px;'><b>RSI (14):</b> <span style='color: {rsi_color}; font-weight: bold;'>{rsi_state}</span></div>"
                    f"<div style='margin-bottom: 8px;'><b>MACD:</b> {macd_state}</div>"
                    f"<div><b>볼린저밴드:</b> <span style='color: #fbbf24;'>{bb_sig}</span></div>"
                    "</div>"
                )
                st.markdown(html_indicators, unsafe_allow_html=True)
                
                if tech_ind.get('Is_Above_Monthly_EMA10'): 
                    st.markdown("<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(52, 211, 153, 0.1); color: #34d399; font-weight: 600;'>🟢 월봉 10선 생명선 위 (안전구간)</div>", unsafe_allow_html=True)
                else: 
                    st.markdown("<div style='margin-top: 15px; padding: 10px; border-radius: 8px; background: rgba(248, 113, 113, 0.1); color: #f87171; font-weight: 600;'>🔴 월봉 10선 생명선 이탈 (위험구간)</div>", unsafe_allow_html=True)
            
        with info_col2:
            st.markdown("<h4 style='color: #f8fafc; font-size: 1.1rem;'>📰 실시간 마켓 내러티브</h4>", unsafe_allow_html=True)
            news_list = get_recent_news(actual_name)[:4]
            news_html = "<div style='display: flex; flex-direction: column; gap: 8px;'>"
            for news in news_list: 
                news_html += f"<div style='background: #1e293b; padding: 10px; border-radius: 8px; font-size: 0.85em; color: #cbd5e1; border-left: 3px solid #64748b;'>{news}</div>"
            news_html += "</div>"
            st.markdown(news_html, unsafe_allow_html=True)
            
            if st.button("📰 AI 뉴스 감성(Sentiment) 스코어 분석", use_container_width=True):
                if not gemini_api_key: st.error("위쪽 시스템 설정에서 API Key를 입력하세요!"); st.stop()
                with st.spinner("AI가 최신 뉴스를 꼼꼼히 읽고 있습니다..."):
                    try:
                        sentiment_res = get_ai_analysis(f"다음 뉴스들의 전반적인 투자 감성을 0~100점으로 평가해줘. 형식(JSON): {{\"score\": 정수, \"verdict\": \"강력 매수/긍정적/중립/부정적/강력 매도\", \"summary\": \"3줄 요약\"}} 뉴스: {news_list}", gemini_api_key)
                        score = sentiment_res.get('score', 50)
                        bar_color = "#34d399" if score >= 60 else "#f87171" if score <= 40 else "#fbbf24"
                        html_sentiment = (
                            f"<div style='background: #0f172a; border: 1px solid {bar_color}; padding: 15px; border-radius: 12px; margin-top: 15px;'>"
                            f"<h4 style='margin-top:0; color:{bar_color};'>🔥 AI 감성 스코어: {score}점 ({sentiment_res.get('verdict', '중립')})</h4>"
                            f"<div style='width: 100%; background-color: #334155; border-radius: 10px; height: 10px; margin-bottom: 10px;'><div style='width: {score}%; background-color: {bar_color}; height: 10px; border-radius: 10px;'></div></div>"
                            f"<p style='font-size:0.9em; color:#cbd5e1;'>{sentiment_res.get('summary', '')}</p>"
                            "</div>"
                        )
                        st.markdown(html_sentiment, unsafe_allow_html=True)
                    except Exception as e: 
                        logging.error(f"뉴스 감성 스코어 분석 실패: {e}")
                        st.error(f"분석 실패: {e}")

        st.markdown("<h3 style='color: #38bdf8; margin-top:30px;'>🤖 Harness 4-Agent 분석 엔진</h3>", unsafe_allow_html=True)
        if st.button("🚀 4-Agent 회 소집 (분석 실행)", type="primary", use_container_width=True):
            if not gemini_api_key: st.error("API Key를 입력하세요!"); st.stop()
            with st.spinner("4명의 AI 전문가가 차트와 뉴스를 분석하며 토론 중입니다..."):
                try:
                    res = get_ai_analysis(f"종목: {actual_name}, 뉴스: {news_list}, 월봉10선: {'안전' if tech_ind.get('Is_Above_Monthly_EMA10') else '위험'}, 성향: {st.session_state.invest_style}. 출력 형식(JSON): {{\"macroAgent\": {{\"score\": 80, \"reasoning\": \"...\"}}, \"technicalAgent\": {{\"score\": 70, \"reasoning\": \"...\"}}, \"fundamentalAgent\": {{\"score\": 60, \"reasoning\": \"...\"}}, \"riskManager\": {{\"action\": \"매수/관망/매도\", \"positionSize\": \"20%\", \"reasoning\": \"...\"}}}}", gemini_api_key)
                    html_chat = (
                        "<div class='chat-container'>"
                        f"<div class='chat-bubble chat-macro'><div class='chat-header'><span>🌍 Agent 1: 거시경제 전략가</span> <span class='score-badge'>Score: {res.get('macroAgent', {}).get('score', 0)}/100</span></div><div style='line-height: 1.6;'>{res.get('macroAgent', {}).get('reasoning', '')}</div></div>"
                        f"<div class='chat-bubble chat-tech'><div class='chat-header'><span>📈 Agent 2: 기술적 분석가</span> <span class='score-badge'>Score: {res.get('technicalAgent', {}).get('score', 0)}/100</span></div><div style='line-height: 1.6;'>{res.get('technicalAgent', {}).get('reasoning', '')}</div></div>"
                        f"<div class='chat-bubble chat-funda'><div class='chat-header'><span>📰 Agent 3: 펀더멘털 매니저</span> <span class='score-badge'>Score: {res.get('fundamentalAgent', {}).get('score', 0)}/100</span></div><div style='line-height: 1.6;'>{res.get('fundamentalAgent', {}).get('reasoning', '')}</div></div>"
                        f"<div class='chat-bubble chat-risk'><div class='chat-header'><span>🛡️ Agent 4: 리스크 총괄 (최종 판단)</span> <span class='score-badge score-badge-risk'>포지션: {res.get('riskManager', {}).get('action', '')} | 비중: {res.get('riskManager', {}).get('positionSize', '')}</span></div><div style='font-weight: 600; color: #fca5a5; line-height: 1.6;'>{res.get('riskManager', {}).get('reasoning', '')}</div></div>"
                        "</div>"
                    )
                    st.markdown(html_chat, unsafe_allow_html=True)
                except Exception as e: 
                    logging.error(f"4-Agent 분석 오류: {e}")
                    st.error(f"분석 오류: {e}")

# -----------------------------------------------------
# [탭 2] 포트폴리오 관리 & 가계부
# -----------------------------------------------------
with tab2:
    p_data = st.session_state.p_data
    ledger_data = st.session_state.ledger_data
    usd_krw = get_exchange_rate()
    
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1: st.markdown(f"<h3 style='color: #f8fafc;'>💼 {st.session_state.user_id}님의 퀀트 포트폴리오</h3>", unsafe_allow_html=True)
    with col_t2: st.markdown(f"<div style='text-align:right; margin-top:20px; font-size:0.9em; color:#94a3b8;'>현재 환율 적용: <span style='color:#38bdf8; font-weight:bold;'>1 USD = {int(usd_krw):,}원</span></div>", unsafe_allow_html=True)
    
    with st.expander("📊 내 계좌 성과 리포트 (월별 수익 캘린더)", expanded=True):
        history_df = pd.DataFrame(ledger_data.get('history', []))
        if not history_df.empty:
            history_df['date'] = pd.to_datetime(history_df['date'])
            monthly_profit = history_df.groupby(history_df['date'].dt.to_period('M'))['profit_krw'].sum().reset_index()
            monthly_profit['date_str'] = monthly_profit['date'].dt.strftime('%Y년 %m월')
            
            fig = go.Figure()
            colors = ['#34d399' if p > 0 else '#f87171' for p in monthly_profit['profit_krw']]
            
            bar_width = [0.25] * len(monthly_profit) if len(monthly_profit) == 1 else None
            
            fig.add_trace(go.Bar(
                x=monthly_profit['date_str'], 
                y=monthly_profit['profit_krw'], 
                marker_color=colors, 
                text=[f"{int(p):,}원" for p in monthly_profit['profit_krw']], 
                textposition='outside', 
                textfont=dict(color='#f8fafc', size=14, family="Arial Black"),
                width=bar_width,
                marker_line_width=0, 
                hovertemplate="<b>%{x}</b><br>총 실현수익: %{text}<extra></extra>"
            ))
            
            y_max = monthly_profit['profit_krw'].max() * 1.3 if monthly_profit['profit_krw'].max() > 0 else 100
            y_min = monthly_profit['profit_krw'].min() * 1.3 if monthly_profit['profit_krw'].min() < 0 else 0
            
            fig.update_layout(
                template="plotly_dark", 
                title=dict(text="📈 월별 누적 실현 수익금", font=dict(size=18, color="#cbd5e1")),
                height=380, 
                margin=dict(l=10, r=10, t=60, b=20),
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    type='category', 
                    showgrid=False,
                    tickfont=dict(color='#94a3b8', size=13)
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='rgba(51, 65, 85, 0.4)', 
                    zeroline=True,
                    zerolinecolor='rgba(255,255,255,0.2)',
                    zerolinewidth=2,
                    tickfont=dict(color='#94a3b8'),
                    range=[y_min, y_max]
                ),
                showlegend=False,
                hoverlabel=dict(bgcolor="#1e293b", font_size=14, bordercolor="#38bdf8")
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            st.markdown("<h4 style='color: #38bdf8; margin-top: 10px; margin-bottom: 15px;'>📝 최근 매도 기록 (가계부)</h4>", unsafe_allow_html=True)
            st.dataframe(history_df.sort_values('date', ascending=False).head(5)[['date', 'ticker', 'profit_krw', 'memo']], 
                         column_config={"date": "매도일자", "ticker": "종목", "profit_krw": st.column_config.NumberColumn("실현수익(원)", format="%d"), "memo": "메모"}, hide_index=True, use_container_width=True)
        else:
            st.info("아직 수익 실현 기록이 없습니다. 첫 매도를 통해 가계부를 채워보세요!")
            
    st.markdown("---")
    
    with st.expander("💰 초기 자본금 세팅 (원화 기준)", expanded=(p_data['initial_capital'] == 0)):
        new_cap = st.number_input("초기 자본금 (원화)", value=int(p_data['initial_capital']), step=1000000)
        if st.button("저장"): p_data['initial_capital'] = new_cap; save_portfolio(p_data); st.rerun()

    total_invested_krw = 0
    for r in p_data['stocks']:
        _, tck = get_stock_info(r['종목명'])
        is_us = not str(tck).isdigit() if tck else False
        ex_rate = usd_krw if is_us else 1.0
        total_invested_krw += (r['매수단가'] * r['수량'] * ex_rate)
        
    remaining_cash = p_data['initial_capital'] + p_data['realized_profit'] - total_invested_krw
    dis_df = pd.DataFrame(p_data['stocks']) if p_data['stocks'] else pd.DataFrame(columns=['종목명', '매수단가', '수량'])
    
    total_unrealized_profit_krw = 0
    total_asset_value_krw = remaining_cash
    
    if not dis_df.empty:
        prices=[]; profs=[]; rates=[]; trailing_stops=[]; currencies=[]
        for _, r in dis_df.iterrows():
            _, tck = get_stock_info(r['종목명'])
            is_us = not str(tck).isdigit() if tck else False
            ex_rate = usd_krw if is_us else 1.0
            
            p, atr = get_portfolio_stock_data(tck)
            
            prof = (p - r['매수단가']) * r['수량']
            rate = (prof / (r['매수단가']*r['수량']) * 100) if r['매수단가']>0 else 0
            
            t_stop = p - (atr * 2.5) if rate > 0 else r['매수단가'] - (atr * 2)
                
            prices.append(p); profs.append(prof); rates.append(rate); trailing_stops.append(t_stop); currencies.append("USD" if is_us else "KRW")
            
            total_unrealized_profit_krw += (prof * ex_rate)
            total_asset_value_krw += (p * r['수량'] * ex_rate)
            
        dis_df['통화'] = currencies
        dis_df['현재가'] = prices; dis_df['수익금'] = profs; dis_df['수익률(%)'] = rates
        dis_df['🛡️손절/익절가'] = trailing_stops 
        dis_df['평가금액'] = np.array(prices) * dis_df['수량'].astype(float)
        
        sector_map = get_sector_map()
        dis_df['섹터'] = [ '해외주식' if c == 'USD' else sector_map.get(n, '기타분류') for c, n in zip(currencies, dis_df['종목명']) ]
        dis_df['원화평가금액'] = [ p * (usd_krw if c == 'USD' else 1.0) for p, c in zip(dis_df['평가금액'], currencies) ]

    html_portfolio_kpi = (
        "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;'>"
        f"<div class='kpi-card' style='padding: 15px;'><div class='kpi-title'>💵 보유 현금</div><div class='kpi-value-main' style='font-size: 1.4rem;'>{int(remaining_cash):,}원</div></div>"
        f"<div class='kpi-card' style='padding: 15px;'><div class='kpi-title'>📦 투자 원금</div><div class='kpi-value-main' style='font-size: 1.4rem;'>{int(total_invested_krw):,}원</div></div>"
        f"<div class='kpi-card' style='padding: 15px; border-color: #38bdf8;'><div class='kpi-title'>💎 총 자산</div><div class='kpi-value-main' style='font-size: 1.4rem; color: #38bdf8;'>{int(total_asset_value_krw):,}원</div></div>"
        f"<div class='kpi-card' style='padding: 15px; border-color: {'#34d399' if total_unrealized_profit_krw > 0 else '#f87171'};'><div class='kpi-title'>📈 평가 손익</div><div class='kpi-value-main' style='font-size: 1.4rem; color: {'#34d399' if total_unrealized_profit_krw > 0 else '#f87171'};'>{int(total_unrealized_profit_krw):,}원</div></div>"
        "</div>"
    )
    st.markdown(html_portfolio_kpi, unsafe_allow_html=True)
    
    if not dis_df.empty:
        sector_val = dis_df.groupby('섹터')['원화평가금액'].sum().reset_index()
        sector_val = sector_val[sector_val['원화평가금액'] > 0]
        
        if not sector_val.empty:
            fig_pie = go.Figure(data=[go.Pie(labels=sector_val['섹터'], values=sector_val['원화평가금액'], hole=.4, textinfo='label+percent', marker=dict(colors=['#38bdf8', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#e879f9']))])
            fig_pie.update_layout(template="plotly_dark", title="📊 나의 자산 배분 현황 (섹터 및 테마 분산도)", height=350, margin=dict(t=40, b=20, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("💡 파이 차트를 그리려면 0원 이상의 포트폴리오 자산이 필요합니다.")

    buy_tab, sell_tab, del_tab = st.tabs(["🛒 매수", "💰 매도", "🗑️ 오류 삭제"])
    with buy_tab:
        with st.form("buy"):
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1: p_n = st.text_input("종목명 (애플, AAPL 등 입력 가능)")
            with bc2: p_p = st.number_input("매수단가 (미국주식은 달러입력)", min_value=0.0)
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
                        _, tck = get_stock_info(s_n)
                        is_us = not str(tck).isdigit() if tck else False
                        ex_rate = usd_krw if is_us else 1.0
                        
                        prof_in_currency = (s_p - p_data['stocks'][idx]['매수단가']) * s_q
                        prof_in_krw = prof_in_currency * ex_rate
                        
                        p_data['realized_profit'] += prof_in_krw
                        p_data['stocks'][idx]['수량'] -= s_q
                        if p_data['stocks'][idx]['수량'] <= 0: p_data['stocks'].pop(idx)
                        
                        new_record = {
                            'id': str(time.time()),
                            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'ticker': s_n,
                            'profit_krw': prof_in_krw,
                            'memo': f"{s_q}주 매도"
                        }
                        ledger_data['history'].append(new_record)
                        
                        save_portfolio(p_data)
                        save_ledger(ledger_data)
                        st.rerun()
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
        st.markdown("<h4 style='color: #38bdf8; margin-top: 30px; margin-bottom: 20px; font-weight: 800;'>📊 실시간 포트폴리오 현황 (스마트 트레일링 가동중)</h4>", unsafe_allow_html=True)
        
        # --- 1. 직관적인 카드 뷰 UI (모바일/웹 친화적) ---
        def fmt_price(val, cur): return f"${val:,.2f}" if cur == 'USD' else f"{int(val):,}원"
        
        cards_html = "<div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; margin-bottom: 30px;'>"
        for _, row in dis_df.iterrows():
            is_profit = row['수익률(%)'] > 0
            is_loss = row['수익률(%)'] < 0
            color = "#f87171" if is_profit else ("#60a5fa" if is_loss else "#94a3b8")
            bg_color = "rgba(248, 113, 113, 0.05)" if is_profit else ("rgba(96, 165, 250, 0.05)" if is_loss else "rgba(148, 163, 184, 0.05)")
            border_color = "rgba(248, 113, 113, 0.3)" if is_profit else ("rgba(96, 165, 250, 0.3)" if is_loss else "rgba(148, 163, 184, 0.3)")
            
            cards_html += f"""
            <div style='background: {bg_color}; border: 1px solid {border_color}; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;'>
                    <h4 style='color: #f8fafc; margin: 0; font-size: 1.25rem; font-weight: 800;'>{row['종목명']}</h4>
                    <span style='background: {color}20; color: {color}; padding: 6px 12px; border-radius: 8px; font-weight: 900; font-size: 1rem;'>
                        {row['수익률(%)']:.2f}%
                    </span>
                </div>
                <div style='display: flex; justify-content: space-between; margin-bottom: 10px;'>
                    <span style='color: #94a3b8; font-size: 0.95rem;'>현재가</span>
                    <span style='color: #f8fafc; font-weight: 700;'>{fmt_price(row['현재가'], row['통화'])}</span>
                </div>
                <div style='display: flex; justify-content: space-between; margin-bottom: 10px;'>
                    <span style='color: #94a3b8; font-size: 0.95rem;'>평가 손익</span>
                    <span style='color: {color}; font-weight: 800;'>{fmt_price(row['수익금'], row['통화'])}</span>
                </div>
                <div style='border-top: 1px dashed rgba(255,255,255,0.1); margin: 15px 0;'></div>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <span style='color: #94a3b8; font-size: 0.95rem;'>🛡️ 트레일링 방어선</span>
                    <span style='color: #fbbf24; font-weight: 800; font-size: 1.1rem;'>{fmt_price(row['🛡️손절/익절가'], row['통화'])}</span>
                </div>
            </div>
            """
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)
        
        # --- 2. 편집 가능한 데이터 테이블 ---
        st.markdown("<p style='color: #94a3b8; font-size: 0.9rem; margin-bottom: 10px;'>💡 <b>매수단가</b>와 <b>수량</b>의 숫자를 더블클릭하여 직접 수정할 수 있습니다.</p>", unsafe_allow_html=True)
        
        # 가독성을 위해 컬럼 순서 직관적으로 재배치
        view_df = dis_df[['종목명', '통화', '매수단가', '수량', '현재가', '수익금', '수익률(%)', '🛡️손절/익절가']]
        
        def highlight_profit(val):
            try:
                v = float(val)
                if v > 0: return 'color: #f87171; font-weight: 800; background-color: rgba(248, 113, 113, 0.05);'
                elif v < 0: return 'color: #60a5fa; font-weight: 800; background-color: rgba(96, 165, 250, 0.05);'
                else: return ''
            except: return ''
            
        try: styled_df = view_df.style.map(highlight_profit, subset=['수익금', '수익률(%)'])
        except AttributeError: styled_df = view_df.style.applymap(highlight_profit, subset=['수익금', '수익률(%)'])

        edt_df = st.data_editor(styled_df, 
            column_config={
                "종목명": st.column_config.TextColumn("📌 종목명", disabled=True),
                "통화": st.column_config.TextColumn("💱 통화", disabled=True),
                "매수단가": st.column_config.NumberColumn("🛒 매수단가", format="%d"),
                "수량": st.column_config.NumberColumn("📦 수량", format="%d"),
                "현재가": st.column_config.NumberColumn("📈 현재가", format="%d", disabled=True), 
                "수익금": st.column_config.NumberColumn("💰 수익금", format="%d", disabled=True), 
                "수익률(%)": st.column_config.NumberColumn("🔥 수익률(%)", format="%.2f", disabled=True),
                "🛡️손절/익절가": st.column_config.NumberColumn("🛡️ 방어선", format="%d", disabled=True)
            }, hide_index=True, use_container_width=True
        )
        
        if str(pd.DataFrame(p_data['stocks'])[['매수단가', '수량']].fillna(0).values.tolist()) != str(edt_df[['매수단가', '수량']].fillna(0).values.tolist()):
            p_data['stocks'] = edt_df[['종목명', '매수단가', '수량']].to_dict('records')
            save_portfolio(p_data); st.rerun()
            
        st.markdown("<h3 style='color: #38bdf8; margin-top:40px;'>🤖 AI VVIP 펀드매니저 리밸런싱 리포트</h3>", unsafe_allow_html=True)
        if st.button("🚀 포트폴리오 종합 진단 및 비중 조절 조언 받기", type="primary", use_container_width=True):
            if not gemini_api_key: 
                st.error("위쪽 시스템 설정에서 API Key를 입력하세요!")
                st.stop()
                
            with st.spinner("AI 펀드매니저가 고객님의 자산 비중과 글로벌 시장 동향을 매칭하여 분석 중입니다..."):
                port_summary = dis_df[['종목명', '섹터', '수익률(%)', '원화평가금액']].to_dict('records')
                news_summary = get_recent_news("주식 시장 시황")
                
                prompt = f"""
                당신은 상위 1% VVIP를 전담하는 수석 AI 펀드매니저입니다.
                고객의 투자 성향: {st.session_state.invest_style}
                시장 주요 뉴스: {news_summary}
                고객 포트폴리오 현황: {port_summary}
                
                이 데이터를 바탕으로 현재 포트폴리오의 건강 상태, 섹터 쏠림 현상 여부, 그리고 종목별 구체적인 리밸런싱(비중 축소/확대) 조언을 분석해주세요.
                [중요] 반드시 아래에 제시된 JSON 형식만을 출력해야 하며, 다른 부가적인 텍스트나 마크다운 기호는 일절 포함하지 마세요.
                {{
                    "portfolio_health": "포트폴리오 종합 평가 및 섹터 분산도 평가 (3문장 내외)",
                    "rebalancing_strategy": "시장 상황에 따른 전체 비중 조절 전략 (2문장 내외)",
                    "action_items": [
                        {{"stock": "종목명", "action": "비중확대/유지/비중축소/전량매도", "reasoning": "액션에 대한 명확한 이유 (1문장)"}}
                    ]
                }}
                """
                try:
                    res = get_ai_analysis(prompt, gemini_api_key)
                    
                    portfolio_health = res.get('portfolio_health', '포트폴리오 상태를 분석할 수 없습니다.')
                    rebalancing_strategy = res.get('rebalancing_strategy', '전략을 분석할 수 없습니다.')
                    action_items = res.get('action_items', [])
                    
                    if isinstance(action_items, dict): action_items = [action_items]
                    elif isinstance(action_items, str) or not isinstance(action_items, list): action_items = []
                    
                    html_report = (
                        "<div style='background: #1e293b; padding: 25px; border-radius: 16px; border: 1px solid #334155; margin-top: 15px; animation: fadeIn 0.5s;'>"
                        "<h4 style='color: #34d399; margin-top: 0; font-size: 1.2rem;'>🩺 포트폴리오 종합 진단</h4>"
                        f"<p style='color: #e2e8f0; line-height: 1.6; margin-bottom: 20px;'>{portfolio_health}</p>"
                        "<h4 style='color: #fbbf24; font-size: 1.2rem;'>⚖️ 핵심 리밸런싱 전략</h4>"
                        f"<p style='color: #e2e8f0; line-height: 1.6; margin-bottom: 25px;'>{rebalancing_strategy}</p>"
                        "<h4 style='color: #38bdf8; font-size: 1.2rem; margin-bottom: 15px;'>🎯 종목별 액션 플랜</h4>"
                        "<div style='display: flex; flex-direction: column; gap: 12px;'>"
                    )
                    
                    if not action_items:
                        html_report += "<div style='color: #94a3b8; font-size: 0.95rem; padding: 10px;'>💡 현재 포트폴리오 구조에서는 특별한 비중 조절(리밸런싱) 액션이 필요하지 않거나, AI가 상세 종목 분석을 보류했습니다.</div>"
                    else:
                        for item in action_items:
                            if not isinstance(item, dict): continue
                            stock_name = str(item.get('stock', '알수없음'))
                            action = str(item.get('action', '유지'))
                            reasoning = str(item.get('reasoning', ''))
                            action_color = "#34d399" if "확대" in action else "#f87171" if "축소" in action or "매도" in action else "#94a3b8"
                            
                            html_report += (
                                f"<div style='background: #0f172a; padding: 15px; border-radius: 12px; border-left: 4px solid {action_color};'>"
                                f"<span style='font-weight: 800; color: #f8fafc; font-size: 1.1rem;'>{stock_name}</span> "
                                f"<span style='background: {action_color}20; color: {action_color}; padding: 4px 10px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; margin-left: 10px;'>{action}</span>"
                                f"<p style='color: #cbd5e1; margin: 8px 0 0 0; font-size: 0.95rem; line-height: 1.5;'>{reasoning}</p>"
                                "</div>"
                            )
                            
                    html_report += "</div></div>"
                    st.markdown(html_report, unsafe_allow_html=True)
                    st.success("✅ VVIP AI 펀드매니저 리포트 생성이 완료되었습니다.")
                except Exception as e:
                    logging.error(f"VVIP 리포트 생성 오류: {e}")
                    st.error(f"🚨 AI 분석 중 오류가 발생했습니다: {str(e)}")
                    st.warning("💡 포트폴리오에 보유 종목이 하나밖에 없거나 구글 AI 서버가 일시적인 혼잡 상태일 수 있습니다. 잠시 후 버튼을 다시 눌러주세요.")

# -----------------------------------------------------
# [탭 3] VIP 스크리너 
# -----------------------------------------------------
with tab3:
    st.markdown("<h3 style='color: #f8fafc;'>📡 매수 급소 AI 스크리너</h3>", unsafe_allow_html=True)
    mode = st.radio("시장 스캔 모드 선택", ["⚡ 한국 우량주 40종목 (무료)", "💎 한국 코스피 상위 200종목 (VIP)", "🚀 한국 코스닥 상위 200종목 (VIP)", "🦅 미국 S&P500 상위 100종목 (VIP)"], horizontal=True)
    
    use_liquidity_filter = st.checkbox("🛡️ 실전 유동성 필터 켜기 (시총 1천억 & 5일평균 거래대금 50억 이상만)", value=False, help="체크 시 세력 장난이 심한 잡주를 걸러냅니다. 끄면 바닥에서 터지는 급등주까지 모두 잡습니다.")
    send_to_telegram = st.checkbox("📱 스캔 완료 시 내 텔레그램으로 전송", value=True)
    
    if st.button("🔎 딥 스캔 실행", type="primary", use_container_width=True):
        if "VIP" in mode and st.session_state.user_tier not in ['VIP', 'Admin']:
            st.error("🔒 **VIP 전용 기능입니다!**\n\n좌측 상단의 **[계정 관리]** 메뉴에서 로그인하시거나, 무료 모드(한국 우량주)를 선택해 주세요.")
            st.warning("💡 테스트를 원하시면 위에 있는 '⚡ 한국 우량주 40종목 (무료)' 모드를 선택하고 검색해보세요.")
            st.stop()
            
        with st.spinner("빅데이터 필터링 중..."):
            if "우량주" in mode: sl = {"삼성전자":"005930", "SK하이닉스":"000660", "카카오":"035720", "현대차":"005380", "NAVER":"035420", "기아":"000270", "셀트리온":"068270", "KB금융":"105560", "POSCO홀딩스":"005490", "LG화학":"051910"}
            elif "코스피" in mode: sl = get_top_200_stocks()
            elif "코스닥" in mode: sl = get_kosdaq_top_200_stocks()
            else: sl = get_us_top_stocks()
            
            sector_map = get_sector_map()
            marcap_dict = {}
            if "미국" not in mode:
                try:
                    krx_df = fdr.StockListing('KRX')
                    marcap_dict = dict(zip(krx_df['Code'], krx_df['Marcap']))
                except Exception as e: 
                    logging.warning(f"스크리너 KRX 시총 로드 오류: {e}")
            
            res = []; bar = st.progress(0); txt = st.empty()
            total_stocks = len(sl) if sl else 1
            
            for i, (n, c) in enumerate(sl.items()):
                txt.text(f"스캔 중... [{n}] ({i+1}/{total_stocks})")
                try:
                    df = fdr.DataReader(c, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
                    df, ind = calculate_cloud_indicators(df)
                    
                    if ind:
                        recent_amount = 0
                        if 'Volume' in df.columns:
                            recent_amount = (df['Close'].tail(5) * df['Volume'].tail(5)).mean()
                        marcap = marcap_dict.get(c, 0)
                        
                        if use_liquidity_filter and "미국" not in mode:
                            if marcap > 0 and marcap < 100000000000: continue
                            if recent_amount < 5000000000: continue

                        sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                        is_smart = ind['MACD_Early_Entry'] or ind['RSI_Turnaround'] or ind['MACD_Cross'] or ind.get('Volume_Explosion')
                        
                        if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                            curr_p = float(df['Close'].iloc[-1])
                            ema5 = float(ind['EMA5'])
                            entry2 = float(ind['EMA15'])
                            entry1 = ema5 if curr_p > ema5 else curr_p
                            a = float(ind['ATR'])
                            tar_p = entry1 + (a*4)
                            stop_p = entry1 - (a*2)
                            
                            denom = entry2 - stop_p
                            rr_2 = (tar_p - entry2) / denom if denom > 1e-5 else 0.0
                            
                            tags = []
                            if ind.get('Cup_and_Handle'): tags.append("☕컵앤핸들")
                            if ind.get('Volume_Explosion'): tags.append("💥수급폭발")
                            if ind['MACD_Early_Entry']: tags.append("🚀선취매")
                            if ind['RSI_Turnaround']: tags.append("📉RSI턴")
                            if ind['MACD_Cross']: tags.append("🟢골든크로스")
                            
                            res.append({
                                "종목명": str(n), 
                                "섹터": sector_map.get(str(n), "기타분류"),
                                "시그널": "🔥 강력매수" if is_smart else "👍 분할매수",
                                "포착원인": " + ".join(tags) if tags else "추세추종",
                                "현재가": float(curr_p), 
                                "1차타점(대기)": float(entry1),
                                "목표가": float(tar_p), 
                                "손절가": float(stop_p), 
                                "손익비(배)": float(rr_2),
                                "RSI": float(ind.get('RSI', 50)),
                                "MACD": "🟢 상승" if ind.get("MACD_Cross", False) else "🔴 하락",
                                "볼린저상태": "🚨 스퀴즈" if ind.get("BB_Is_Squeeze") else "확장",
                                "시총(억)": int(marcap / 100000000) if marcap > 0 else 0,
                                "거래대금(억)": int(recent_amount / 100000000) if not pd.isna(recent_amount) else 0
                            })
                except Exception as e:
                    logging.info(f"스크리닝 종목 건너뜀 ({n}): {e}")
                    pass
                
                safe_progress = min((i + 1) / total_stocks, 1.0)
                if 0.0 <= safe_progress <= 1.0:
                    bar.progress(safe_progress)
                    
            txt.text("✅ 스캔 완료!")
            
            if res:
                st.session_state.scan_results = res
                
                if send_to_telegram:
                    is_us = "미국" in mode
                    if tele_token and tele_chat_id:
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
                        
                        telegram_success = True
                        for c in chunks: 
                            if not send_telegram_message(tele_token, tele_chat_id, c):
                                telegram_success = False
                            time.sleep(0.3)
                            
                        if telegram_success: st.success("📱 텔레그램 전송 완료!")
                        else: st.error("🚨 텔레그램 전송 실패! [계정 관리] 탭에서 Bot 토큰과 Chat ID를 확인해 주세요.")
                    else: st.warning("⚠️ 텔레그램 전송 생략: 봇 토큰(Token) 또는 챗 아이디(Chat ID)가 없습니다.")

            else: 
                st.session_state.scan_results = []
                st.info("💡 스캔을 완료했으나, 현재 조건(월봉 10선 위 안전구간)을 통과한 종목이 없습니다.")

    if st.session_state.scan_results:
        df_all = pd.DataFrame(st.session_state.scan_results)
        if not df_all.empty and '섹터' in df_all.columns:
            total_count = len(df_all)
            
            meaningful_df = df_all[~df_all['섹터'].isin(['기타분류', '제조/기타산업'])]
            
            if not meaningful_df.empty:
                sector_counts = meaningful_df['섹터'].value_counts()
                if not sector_counts.empty:
                    top_sector = sector_counts.index[0]
                    top_count = sector_counts.iloc[0]
                    top_ratio = (top_count / total_count) * 100
                    
                    if top_count >= 2:
                        st.markdown(f"""
                        <div style='background: linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(15, 23, 42, 0.8)); border-left: 4px solid #ef4444; padding: 20px; border-radius: 12px; margin-top: 25px; margin-bottom: 25px; border-right: 1px solid #334155; border-top: 1px solid #334155; border-bottom: 1px solid #334155;'>
                            <h4 style='color: #f8fafc; margin-top: 0; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                                🔥 <span style='color: #ef4444;'>AI 수급 쏠림 감지 엔진</span>
                            </h4>
                            <p style='color: #e2e8f0; font-size: 1.05rem; margin: 0; line-height: 1.6;'>
                                오늘 타점이 포착된 <strong>{total_count}개</strong> 종목 중 <strong style='color: #fcd34d; font-size: 1.2rem; background: rgba(252, 211, 77, 0.1); padding: 2px 6px; border-radius: 4px;'>{top_count}개 ({top_ratio:.1f}%)</strong>가 <strong>[{top_sector}]</strong> 섹터에 집중되어 있습니다!<br>
                                <span style='color: #94a3b8; font-size: 0.9rem; margin-top: 8px; display: inline-block;'>💡 스마트 머니(메이저 수급)가 해당 섹터로 강하게 유입 중일 확률이 높습니다. <strong>{top_sector}</strong> 관련주를 1순위로 확인하세요.</span>
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    
        st.markdown("<h4 style='color:#f8fafc; margin-top:30px; margin-bottom: 15px;'>🎯 맞춤형 전략 필터링 (결과 내 즉시 검색)</h4>", unsafe_allow_html=True)
        
        filter_mode = st.radio("전략 선택", 
            ["🌟 전체 보기", "🔥 S급 돌파 (스퀴즈 + MACD상승)", "☕ 컵 앤 핸들 (U자 반등 후 돌파)", "📉 낙폭과대 (RSI 바닥턴)", "💥 수급폭발 (당일 주도주)"], 
            horizontal=True, label_visibility="collapsed"
        )
        
        num_cols = df_all.select_dtypes(include=[np.number]).columns
        df_all[num_cols] = df_all[num_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
        
        if "S급 돌파" in filter_mode:
            df_view = df_all[(df_all['볼린저상태'].str.contains('스퀴즈')) & (df_all['MACD'].str.contains('상승'))]
        elif "컵 앤 핸들" in filter_mode:
            df_view = df_all[df_all['포착원인'].str.contains('컵앤핸들')]
        elif "낙폭과대" in filter_mode:
            df_view = df_all[df_all['포착원인'].str.contains('RSI턴')]
        elif "수급폭발" in filter_mode:
            df_view = df_all[df_all['포착원인'].str.contains('수급폭발')]
        else:
            df_view = df_all
            
        st.markdown(f"<h4 style='color:#34d399; margin-top:20px;'>✨ 필터링 통과 종목 리스트 (총 {len(df_view)}개)</h4>", unsafe_allow_html=True)
        
        if len(df_view) > 0:
            is_us = "미국" in mode if 'mode' in locals() else False
            currency_format = "%.2f" if is_us else "%d"
            col_suffix = "(달러)" if is_us else "(원)"
            
            st.dataframe(df_view, 
                column_config={
                    "종목명": st.column_config.TextColumn("종목명", width="medium"),
                    "섹터": st.column_config.TextColumn("섹터/테마", width="medium"), 
                    "시그널": st.column_config.TextColumn("AI 시그널"),
                    "포착원인": st.column_config.TextColumn("🔥포착원인", width="large"),
                    "현재가": st.column_config.NumberColumn(f"현재가{col_suffix}", format=currency_format),
                    "1차타점(대기)": st.column_config.NumberColumn(f"1차 매수{col_suffix}", format=currency_format),
                    "목표가": st.column_config.NumberColumn(f"목표가{col_suffix}", format=currency_format),
                    "손절가": st.column_config.NumberColumn(f"손절가{col_suffix}", format=currency_format),
                    "손익비(배)": st.column_config.NumberColumn("손익비", format="%.1f"),
                    "RSI": st.column_config.ProgressColumn("RSI 모멘텀", min_value=0, max_value=100, format="%.1f"),
                    "MACD": st.column_config.TextColumn("MACD 추세"),
                    "볼린저상태": st.column_config.TextColumn("볼린저 밴드"),
                    "시총(억)": st.column_config.NumberColumn("시가총액(억)", format="%d"),
                    "거래대금(억)": st.column_config.NumberColumn("평균 거래대금(억)", format="%d")
                }, 
                hide_index=True, use_container_width=True
            )
            st.download_button("📥 현재 표 CSV 추출", data=df_view.to_csv(index=False).encode('utf-8-sig'), file_name=f"quant_filtered_{len(df_view)}.csv", mime="text/csv")
        else:
            st.warning("이 필터 조건에 해당하는 종목이 없습니다. 다른 필터를 선택해 보세요.")

# -----------------------------------------------------
# [탭 4] Admin (최고 관리자 DB 관리 시스템)
# -----------------------------------------------------
if is_admin:
    with tab4:
        st.markdown("<h3 style='color: #f8fafc;'>🛠️ 최고 관리자 시스템</h3>", unsafe_allow_html=True)
        if db:
            users_stream = db.collection('users').stream()
            user_list = [{"아이디": u.id, "등급": u.to_dict().get("tier", "Free"), "가입일": str(u.to_dict().get("created_at", ""))[:16]} for u in users_stream]
            
            if user_list:
                df_users = pd.DataFrame(user_list)
                
                st.markdown("<h4 style='color: #38bdf8; margin-top: 20px;'>🔄 회원 등급 관리</h4>", unsafe_allow_html=True)
                st.write("표에서 '등급' 열을 클릭하여 Free / VIP / Admin 중 하나로 변경한 뒤, 아래 저장 버튼을 누르세요.")
                
                edited_df = st.data_editor(
                    df_users, 
                    column_config={
                        "아이디": st.column_config.TextColumn("아이디 (이메일)", disabled=True),
                        "등급": st.column_config.SelectboxColumn("등급 (권한)", options=["Free", "VIP", "Admin"]),
                        "가입일": st.column_config.TextColumn("가입일시", disabled=True)
                    },
                    hide_index=True, 
                    use_container_width=True
                )
                
                if st.button("💾 변경된 등급 저장", type="primary"):
                    with st.spinner("권한을 업데이트하고 있습니다..."):
                        update_count = 0
                        for index, row in edited_df.iterrows():
                            original_tier = df_users.iloc[index]['등급']
                            new_tier = row['등급']
                            if original_tier != new_tier:
                                db.collection('users').document(row['아이디']).update({'tier': new_tier})
                                update_count += 1
                        
                        if update_count > 0:
                            st.success(f"✅ {update_count}명의 회원 등급이 성공적으로 업데이트되었습니다!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.info("변경된 내용이 없습니다.")
                
                st.markdown("---")
                
                st.markdown("<h4 style='color: #f87171;'>🗑️ 회원 영구 삭제</h4>", unsafe_allow_html=True)
                with st.form("delete_user_form"):
                    col_d1, col_d2 = st.columns([3, 1])
                    with col_d1:
                        del_user_id = st.selectbox("삭제할 계정을 선택하세요", df_users['아이디'].tolist())
                    with col_d2:
                        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                        del_submit = st.form_submit_button("계정 삭제", use_container_width=True)
                    
                    if del_submit:
                        if del_user_id.lower() == 'admin':
                            st.error("🚨 최고 관리자(admin) 계정은 삭제할 수 없습니다!")
                        else:
                            db.collection('users').document(del_user_id).delete()
                            st.success(f"✅ '{del_user_id}' 계정이 영구 삭제되었습니다.")
                            time.sleep(1)
                            st.rerun()
            else: 
                st.info("가입된 회원이 없습니다.")
        else: 
            st.error("🚨 Firebase 클라우드 DB가 연결되지 않았습니다.")
