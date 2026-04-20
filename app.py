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

# ==========================================
# 1. 페이지 및 세션(포트폴리오) 초기화
# ==========================================
st.set_page_config(page_title="3-Agent Quant Dashboard (Advanced)", layout="wide", page_icon="📈")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame(columns=['종목명', '매수단가', '수량'])

st.sidebar.title("⚙️ 시스템 설정")

if "GEMINI_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 시스템에 API 키가 연동되었습니다.")
else:
    gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Google AI Studio 발급 키")

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 빠른 분석 (Watchlist)")
fast_search = st.sidebar.radio("관심 종목 바로가기", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "아난티"])
if fast_search == "직접 입력":
    stock_name = st.sidebar.text_input("분석할 종목명 (또는 6자리 코드)", "삼성전자")
else:
    stock_name = fast_search

# ==========================================
# 2. 데이터 수집 및 퀀트 지표 계산 함수 ⭐ (핵심 업그레이드)
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
        "NAVER": "035420", "카카오": "035720", "아난티": "025980", 
        "에코프로": "086520", "에코프로비엠": "247540", "앤디포스": "238090"
    }
    if query in top_stocks: return query, top_stocks[query]
    for name, code in top_stocks.items():
        if query == code: return name, code
        
    try:
        url = f"https://ac.finance.naver.com/ac?q={query}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        items = response.json().get('items', [])
        if items and len(items[0]) > 0: return items[0][0][0], items[0][0][1]
    except: pass
    
    if query.isdigit() and len(query) == 6: return query, query
    return None, None

@st.cache_data(ttl=3600)
def get_recent_news(keyword):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, 'xml') # html.parser 대신 xml 파서 권장
        items = soup.find_all('item')
        news_list = [item.title.text for item in items[:5] if item.title]
        return news_list if news_list else ["최신 관련 뉴스를 찾지 못했습니다."]
    except Exception as e:
        return [f"뉴스 수집 중 오류 발생: {e}"]

# 💡 신규 추가: 보조지표(RSI, MA) 파이썬 자동 계산
def calculate_technical_indicators(df):
    if df is None or len(df) < 20: return df, {}
    
    # 20일 이동평균선
    df['MA20'] = df['Close'].rolling(window=20).mean()
    
    # RSI (14일) 계산 로직
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 거래량 급증 확인 (최근 거래량이 20일 평균보다 2배 이상인지)
    df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
    
    latest = df.iloc[-1]
    indicators = {
        "RSI": round(latest['RSI'], 2) if not pd.isna(latest['RSI']) else 50,
        "MA20_Trend": "상승" if latest['Close'] > latest['MA20'] else "하락",
        "Volume_Surge": "급증" if latest['Volume'] > (latest['Vol_MA20'] * 2) else "평범"
    }
    return df, indicators

# 💡 신규 추가: 시장 상황(KOSPI) 체크 함수
@st.cache_data(ttl=3600)
def get_market_trend():
    try:
        ks11 = fdr.DataReader('KS11', datetime.today() - timedelta(days=20), datetime.today())
        start_price = ks11['Close'].iloc[0]
        end_price = ks11['Close'].iloc[-1]
        return "상승장 (Bull)" if end_price > start_price else "하락장 (Bear)"
    except: return "알 수 없음"

@st.cache_data(ttl=3600, show_spinner=False)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

def get_current_price(ticker):
    try:
        df = fdr.DataReader(ticker, datetime.today() - timedelta(days=5), datetime.today())
        return int(df['Close'].iloc[-1]) if not df.empty else 0
    except: return 0

# ==========================================
# 3. 메인 대시보드 UI
# ==========================================
st.title("🤖 Advanced 3-Agent 퀀트 대시보드")
st.markdown("수익률 극대화를 위한 **RSI/MA 보조지표** 및 **코스피 시장 분석** 결합형 AI")

tab1, tab2 = st.tabs(["📊 AI 퀀트 분석", "💼 내 포트폴리오 관리"])

with tab1:
    if not gemini_api_key:
        st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력해야 합니다.")
        st.stop()

    actual_name, ticker = get_stock_info(stock_name)
    if not ticker:
        st.error(f"'{stock_name}'의 종목 코드를 찾을 수 없습니다.")
        st.stop()

    st.subheader(f"📊 {actual_name} ({ticker}) 실시간 데이터")
    col1, col2 = st.columns([2, 1])

    with col1:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=120) # 지표 계산을 위해 120일치 넉넉히
        with st.spinner("주가 및 보조지표 데이터 로딩 중..."):
            try: 
                raw_df = fdr.DataReader(ticker, start_date, end_date)
                df, tech_ind = calculate_technical_indicators(raw_df)
                market_trend = get_market_trend()
            except Exception: df = None; tech_ind = {}; market_trend = "알 수 없음"
            
        if df is not None and not df.empty:
            display_df = df.tail(60) # 차트는 60일치만
            fig = go.Figure(data=[go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="캔들")])
            # MA20 선 추가
            fig.add_trace(go.Scatter(x=display_df.index, y=display_df['MA20'], mode='lines', line=dict(color='orange', width=2), name='20일선(MA20)'))
            fig.update_layout(title="최근 60일 캔들스틱 및 이동평균선", xaxis_rangeslider_visible=False, height=400, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**🧠 파이썬 연산 데이터 (AI 주입용)**")
        st.info(f"📈 **RSI (14일):** {tech_ind.get('RSI', 'N/A')} \n*(30이하 과매도, 70이상 과매수)*")
        st.info(f"선세: **20일선 {tech_ind.get('MA20_Trend', 'N/A')}** / 거래량: **{tech_ind.get('Volume_Surge', 'N/A')}**")
        st.info(f"🌐 **현재 코스피 흐름:** {market_trend}")
        
        st.markdown("**📰 최근 뉴스 헤드라인**")
        news_items = get_recent_news(actual_name)
        for i, news in enumerate(news_items[:3]): st.caption(f"{i+1}. {news}")

    # AI 분석 실행
    st.markdown("---")
    if df is not None and not df.empty:
        if st.button("🚀 수익률 극대화 3-Agent 분석 실행", type="primary", use_container_width=True):
            with st.spinner("수학적 보조지표와 뉴스를 융합하여 승률이 높은 타점을 계산 중입니다..."):
                recent_close = df['Close'].iloc[-1]
                
                # 💡 승률을 높이기 위한 초강력 프롬프트
                prompt = f"""
                당신은 월스트리트 상위 1% 퀀트 트레이딩 시스템 'Harness 3-Agent'입니다.
                감정이나 추측을 배제하고 아래 제시된 '수학적 지표'와 '거시 경제 추세'를 바탕으로 철저히 수익률(기댓값) 위주의 분석을 하세요.

                [분석 대상 팩트 데이터]
                - 종목명: {actual_name} (현재가: {recent_close}원)
                - RSI 지표(14일): {tech_ind.get('RSI')} (30 이하는 바닥 과매도, 70 이상은 상투 과매수)
                - 단기 추세(MA20 기준): {tech_ind.get('MA20_Trend')}
                - 거래량 동향: {tech_ind.get('Volume_Surge')} (급증 시 모멘텀 발생 의미)
                - KOSPI 시장 흐름: {market_trend} (하락장이면 보수적 접근 필수)
                - 최신 뉴스 동향: {news_items}

                [에이전트 역할 및 규칙]
                1. technicalAgent (기술적 분석가): 반드시 'RSI 수치'와 'MA20', '거래량'을 근거로 점수(-10~10)와 타점을 도출할 것. RSI가 30 근처면 반등(매수)에 높은 점수를, 70 근처면 하락(매도)에 점수를 줄 것.
                2. fundamentalAgent (기본적 분석가): 뉴스의 단기적 호재/악재 스코어(-10~10)를 도출할 것.
                3. riskManager (리스크 관리자): 위 두 의견을 취합하되, "기대 수익이 손절폭보다 2배 이상 큰가?"를 따져 [강력매수/분할매수/관망/분할매도/전량매도] 중 1개를 선택할 것. KOSPI가 하락장이면 비중(Position)을 절반 이하로 강제 축소할 것.

                [출력 형식 - 순수 JSON만]
                {{"technicalAgent": {{"score": 5, "reasoning": "RSI가 35로 과매도 구간에 진입하여 기술적 반등 확률이 높습니다..."}}, "fundamentalAgent": {{"score": 8, "reasoning": "..."}}, "riskManager": {{"action": "분할매수", "positionSize": "20%", "reasoning": "..."}}}}
                """
                
                try:
                    result = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 승률 기반 AI 퀀트 분석 완료!")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("### 📈 기술적 분석가")
                        st.metric("기술적 모멘텀", f"{result['technicalAgent']['score']}점")
                        st.write(result['technicalAgent']['reasoning'])
                    with c2:
                        st.markdown("### 📰 기본적 분석가")
                        st.metric("펀더멘털 / 뉴스", f"{result['fundamentalAgent']['score']}점")
                        st.write(result['fundamentalAgent']['reasoning'])
                    with c3:
                        st.markdown("### 🛡️ 리스크 관리자 (최종)")
                        action_color = "🔴" if "매수" in result['riskManager']['action'] else ("🔵" if "매도" in result['riskManager']['action'] else "⚪")
                        st.metric(f"최종 타점 {action_color}", f"{result['riskManager']['action']}")
                        st.markdown(f"**진입 비중:** `{result['riskManager']['positionSize']}`")
                        st.write(result['riskManager']['reasoning'])
                    
                    st.markdown("---")
                    st.markdown("### 💬 카카오톡 공유 (지표 포함)")
                    share_text = f"""🤖 승률 기반 AI 퀀트 리포트: [{actual_name}]

👉 최종 타점: {result['riskManager']['action']} (비중: {result['riskManager']['positionSize']})

📊 분석 근거 팩트:
- RSI(14일): {tech_ind.get('RSI')} (30이하 바닥권, 70이상 상투)
- 20일선 추세: {tech_ind.get('MA20_Trend')} / 코스피: {market_trend}

💡 AI 매니저 종합 의견:
{result['riskManager']['reasoning']}"""
                    
                    st.code(share_text, language="markdown")

                except Exception as e:
                    st.error(f"오류 발생: {e}")

# ------------------------------------------
# [탭 2] 내 포트폴리오 관리 및 진단 (이전 버전과 동일 유지)
# ------------------------------------------
with tab2:
    st.subheader("💼 현재 보유 종목 관리 및 AI 타점 진단")
    st.markdown("내가 매수한 종목을 등록하고 실시간 수익률 확인 및 매도/홀딩 전략을 세워보세요.")
    
    with st.form("add_stock_form"):
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        with col_p1: p_name = st.text_input("종목명 (또는 코드)", "현대차")
        with col_p2: p_price = st.number_input("매수 단가(원)", min_value=0, step=1000)
        with col_p3: p_qty = st.number_input("수량(주)", min_value=1, step=1)
        with col_p4: 
            st.write(""); st.write("")
            submitted = st.form_submit_button("➕ 종목 추가")
            
        if submitted:
            actual_n, _ = get_stock_info(p_name)
            display_name = actual_n if actual_n else p_name
            new_row = pd.DataFrame({'종목명': [display_name], '매수단가': [p_price], '수량': [p_qty]})
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
            st.success(f"'{display_name}' 종목이 포트폴리오에 추가되었습니다!")

    if not st.session_state.portfolio.empty:
        st.markdown("### 📈 실시간 수익률 현황 (✏️ 수정/삭제 가능)")
        display_df = st.session_state.portfolio.copy()
        current_prices = []; profits = []; profit_rates = []
        
        for idx, row in display_df.iterrows():
            actual_n, tck = get_stock_info(row['종목명'])
            cur_p = get_current_price(tck) if tck else 0
            buy_total = row['매수단가'] * row['수량']
            cur_total = cur_p * row['수량']
            profit = cur_total - buy_total
            rate = (profit / buy_total * 100) if buy_total > 0 else 0
            
            current_prices.append(cur_p)
            profits.append(profit)
            profit_rates.append(rate)
            
        display_df['현재가'] = current_prices
        display_df['수익금'] = profits
        display_df['수익률(%)'] = profit_rates
        
        edited_df = st.data_editor(
            display_df,
            column_config={
                "종목명": st.column_config.TextColumn("종목명", disabled=True),
                "매수단가": st.column_config.NumberColumn("매수단가(원)", min_value=0),
                "수량": st.column_config.NumberColumn("수량(주)", min_value=1),
                "현재가": st.column_config.NumberColumn("현재가(원)", disabled=True),
                "수익금": st.column_config.NumberColumn("수익금(원)", disabled=True),
                "수익률(%)": st.column_config.NumberColumn("수익률(%)", format="%.2f%%", disabled=True),
            },
            hide_index=True, use_container_width=True, key="portfolio_editor"
        )
        
        has_changed = False
        for i in range(len(st.session_state.portfolio)):
            if (st.session_state.portfolio.iloc[i]['매수단가'] != edited_df.iloc[i]['매수단가'] or 
                st.session_state.portfolio.iloc[i]['수량'] != edited_df.iloc[i]['수량']):
                has_changed = True; break
                
        if has_changed:
            st.session_state.portfolio['매수단가'] = edited_df['매수단가']
            st.session_state.portfolio['수량'] = edited_df['수량']
            st.rerun()

        st.markdown("#### 🗑️ 개별 종목 삭제")
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            del_target = st.selectbox("포트폴리오에서 지울 종목을 선택하세요", ["선택 안함"] + display_df['종목명'].tolist(), label_visibility="collapsed")
        with col_del2:
            if st.button("❌ 삭제", use_container_width=True) and del_target != "선택 안함":
                st.session_state.portfolio = st.session_state.portfolio[st.session_state.portfolio['종목명'] != del_target]
                st.rerun()

        st.markdown("---")
        st.markdown("### 🤖 보유 종목 타점 진단 (승률 기반)")
        if st.button("✨ 내 포트폴리오 전체 진단받기", type="primary", use_container_width=True):
            with st.spinner("최적의 대응 전략을 계산 중입니다..."):
                pf_text = ""
                for idx, row in display_df.iterrows():
                    pf_text += f"- {row['종목명']}: 매수단가 {row['매수단가']}, 현재가 {row['현재가']}, 수익률 {row['수익률(%)']:.2f}%\n"
                
                prompt = f"""
                당신은 냉철한 퀀트 투자 리스크 관리자입니다.
                사용자의 현재 포트폴리오 수익률을 바탕으로 각 종목의 '매도/부분매도/홀딩/추가매수' 타점과 이유를 진단하세요.
                수익률 +10% 이상은 무조건 절반 익절 권고, -5% 이하는 기계적 손절을 강력히 경고하는 등 냉정하게 1~2문장으로 조언하세요.
                [포트폴리오 현황]\n{pf_text}
                [출력 형식 - JSON]\n{{"results": [{{"stock": "종목명", "action": "부분매도", "reason": "..."}}]}}
                """
                try:
                    genai.configure(api_key=gemini_api_key)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    ai_result = json.loads(response.text)
                    st.success("✅ 포트폴리오 타점 진단 완료!")
                    for item in ai_result.get("results", []):
                        action_color = "🔴" if "매도" in item["action"] else ("🔵" if "홀딩" in item["action"] else "🟢")
                        st.info(f"**{item['stock']}** 👉 {action_color} **{item['action']}** : {item['reason']}")
                except Exception as e: st.error(f"오류 발생: {e}")
                    
        st.write("") 
        if st.button("🗑️ 전체 초기화 (모두 지우기)"):
            st.session_state.portfolio = pd.DataFrame(columns=['종목명', '매수단가', '수량'])
            st.rerun()
    else: st.info("아직 등록된 종목이 없습니다.")
