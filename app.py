import streamlit as st
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import pandas as pd

# ==========================================
# 1. 페이지 및 세션(포트폴리오) 초기화
# ==========================================
st.set_page_config(page_title="3-Agent Quant Dashboard", layout="wide", page_icon="📈")

# 포트폴리오 데이터를 저장할 세션 초기화
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame(columns=['종목명', '매수단가', '수량'])

st.sidebar.title("⚙️ 시스템 설정")

# API 키 자동 연동 로직 (Method B)
if "GEMINI_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 시스템에 API 키가 안전하게 연동되었습니다.")
else:
    gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Google AI Studio에서 발급받은 API 키를 입력하세요.")

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 빠른 분석 (Watchlist)")
# 빠른 검색 칩버튼
fast_search = st.sidebar.radio("관심 종목 바로가기", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "아난티"])
if fast_search == "직접 입력":
    stock_name = st.sidebar.text_input("분석할 종목명 (또는 6자리 코드)", "삼성전자")
else:
    stock_name = fast_search

# ==========================================
# 2. 데이터 수집 & AI 유틸리티 함수
# ==========================================
@st.cache_data(ttl=86400) # 종목 코드는 하루(86400초) 동안 캐싱
def get_stock_ticker(name):
    name = name.strip()
    if name.isdigit() and len(name) == 6: return name
        
    top_stocks = {
        "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
        "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
        "셀트리온": "068270", "POSCO홀딩스": "005490", "KB금융": "105560",
        "NAVER": "035420", "네이버": "035420", "카카오": "035720", 
        "아난티": "025980", "에코프로": "086520", "에코프로비엠": "247540"
    }
    if name in top_stocks: return top_stocks[name]
        
    try:
        url = f"https://ac.finance.naver.com/ac?q={name}&q_enc=utf-8&st=111&r_format=json&r_enc=utf-8"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=5)
        items = response.json().get('items', [])
        if items and len(items[0]) > 0: return items[0][0][1]
    except Exception: pass
    return None

@st.cache_data(ttl=3600) # 뉴스는 1시간 동안 캐싱
def get_recent_news(keyword):
    url = f"https://search.naver.com/search.naver?where=news&query={keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        news_list = [article.text for article in soup.select(".news_tit")[:4]]
        return news_list if news_list else ["최신 관련 뉴스가 없습니다."]
    except Exception as e:
        return [f"뉴스 수집 중 오류 발생: {e}"]

@st.cache_data(ttl=3600, show_spinner=False) # AI 분석 결과 1시간 캐싱 (비용/속도 최적화)
def get_ai_analysis(prompt, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

def get_current_price(ticker):
    try:
        df = fdr.DataReader(ticker, datetime.today() - timedelta(days=5), datetime.today())
        return int(df['Close'].iloc[-1]) if not df.empty else 0
    except:
        return 0

# ==========================================
# 3. 메인 대시보드 UI (탭 구조)
# ==========================================
st.title("🤖 Harness 3-Agent AI 퀀트 대시보드")
st.markdown("전 종목 실시간 데이터 분석 및 포트폴리오 관리 시스템")

tab1, tab2 = st.tabs(["📊 AI 퀀트 분석", "💼 내 포트폴리오 관리"])

# ------------------------------------------
# [탭 1] AI 퀀트 분석 및 카톡 공유
# ------------------------------------------
with tab1:
    if not gemini_api_key:
        st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력해야 분석을 시작할 수 있습니다.")
        st.stop()

    ticker = get_stock_ticker(stock_name)
    if not ticker:
        st.error(f"'{stock_name}'의 종목 코드를 찾을 수 없습니다.")
        st.stop()

    st.subheader(f"📊 {stock_name} ({ticker}) 실시간 데이터")
    col1, col2 = st.columns([2, 1])

    with col1:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=90)
        with st.spinner("주가 데이터를 불러오는 중..."):
            try: df = fdr.DataReader(ticker, start_date, end_date)
            except Exception: df = None
            
        if df is not None and not df.empty:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(title="최근 3개월 캔들스틱 차트", xaxis_rangeslider_visible=False, height=400, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**📰 최근 주요 뉴스 헤드라인**")
        news_items = get_recent_news(stock_name)
        for i, news in enumerate(news_items): st.info(f"{i+1}. {news}")

    # AI 분석 실행
    st.markdown("---")
    if df is not None and not df.empty:
        if st.button("🚀 3-Agent AI 분석 실행", type="primary", use_container_width=True):
            with st.spinner("3명의 AI 에이전트가 데이터를 토론 중입니다 (이전에 분석된 종목이면 즉시 뜹니다!)..."):
                recent_prices = df['Close'].tail(5).tolist()
                price_trend = "상승 추세" if recent_prices[-1] > recent_prices[0] else "하락 추세"
                
                prompt = f"""
                당신은 'Harness 3-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다. 아래 주식 데이터를 분석하세요.
                [종목명: {stock_name}, 5일 종가: {recent_prices}, 추세: {price_trend}, 뉴스: {news_items}]
                [에이전트 역할]
                1. technicalAgent: 차트/모멘텀 분석 점수(-10~10) 및 의견
                2. fundamentalAgent: 기업/뉴스 펀더멘털 점수(-10~10) 및 의견
                3. riskManager: 매수/관망/매도, 권장 비중(%), 최종 결론
                [반드시 JSON 포맷으로 응답]
                {{"technicalAgent": {{"score": 5, "reasoning": "..."}}, "fundamentalAgent": {{"score": 8, "reasoning": "..."}}, "riskManager": {{"action": "매수", "positionSize": "30%", "reasoning": "..."}}}}
                """
                
                try:
                    result = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ AI 분석 완료!")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("### 📈 기술적 분석가")
                        st.metric("스코어", f"{result['technicalAgent']['score']}점")
                        st.write(result['technicalAgent']['reasoning'])
                    with c2:
                        st.markdown("### 📰 기본적 분석가")
                        st.metric("스코어", f"{result['fundamentalAgent']['score']}점")
                        st.write(result['fundamentalAgent']['reasoning'])
                    with c3:
                        st.markdown("### 🛡️ 리스크 관리자 (최종)")
                        st.metric(f"판정", f"{result['riskManager']['action']}")
                        st.markdown(f"**권장 비중:** `{result['riskManager']['positionSize']}`")
                        st.write(result['riskManager']['reasoning'])
                    
                    # 카톡 공유용 텍스트 생성
                    st.markdown("---")
                    st.markdown("### 💬 카카오톡 공유하기")
                    share_text = f"""🤖 3-Agent AI 퀀트 리포트: [{stock_name}]

👉 최종 판정: {result['riskManager']['action']} (권장비중: {result['riskManager']['positionSize']})
📈 기술적 점수: {result['technicalAgent']['score']}점 / 10점
📰 기본적 점수: {result['fundamentalAgent']['score']}점 / 10점

💡 AI 핵심 요약:
{result['riskManager']['reasoning']}"""
                    
                    st.code(share_text, language="markdown")
                    st.caption("☝️ 위 검은색 박스 우측 상단의 '복사' 버튼을 눌러 카톡에 바로 붙여넣으세요!")

                except Exception as e:
                    st.error(f"오류 발생: {e}")

# ------------------------------------------
# [탭 2] 내 포트폴리오 관리 및 진단
# ------------------------------------------
with tab2:
    st.subheader("💼 현재 보유 종목 관리 및 AI 타점 진단")
    st.markdown("내가 매수한 종목을 등록하고 실시간 수익률 확인 및 매도/홀딩 전략을 세워보세요.")
    
    # 종목 추가 폼
    with st.form("add_stock_form"):
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        with col_p1: p_name = st.text_input("종목명", "현대차")
        with col_p2: p_price = st.number_input("매수 단가(원)", min_value=0, step=1000)
        with col_p3: p_qty = st.number_input("수량(주)", min_value=1, step=1)
        with col_p4: 
            st.write("") # 버튼 위치 맞추기
            st.write("")
            submitted = st.form_submit_button("➕ 종목 추가")
            
        if submitted:
            new_row = pd.DataFrame({'종목명': [p_name], '매수단가': [p_price], '수량': [p_qty]})
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
            st.success(f"'{p_name}' 종목이 포트폴리오에 추가되었습니다!")

    # 포트폴리오 현황 테이블 표시
    if not st.session_state.portfolio.empty:
        st.markdown("### 📈 실시간 수익률 현황")
        
        display_df = st.session_state.portfolio.copy()
        current_prices = []
        profits = []
        profit_rates = []
        
        for idx, row in display_df.iterrows():
            tck = get_stock_ticker(row['종목명'])
            cur_p = get_current_price(tck) if tck else 0
            
            # 수익 계산
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
        
        display_df_view = display_df.copy()
        display_df_view['매수단가'] = display_df_view['매수단가'].apply(lambda x: f"{int(x):,}원")
        display_df_view['현재가'] = display_df_view['현재가'].apply(lambda x: f"{int(x):,}원")
        display_df_view['수익금'] = display_df_view['수익금'].apply(lambda x: f"{int(x):,}원")
        display_df_view['수익률(%)'] = display_df_view['수익률(%)'].apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(display_df_view, use_container_width=True)
        
        # ==========================================
        # 💡 AI 포트폴리오 매도/홀딩 타점 진단
        # ==========================================
        st.markdown("---")
        st.markdown("### 🤖 보유 종목 AI 타점 진단")
        st.caption("현재 수익률을 바탕으로 AI 리스크 관리자가 기계적인 손절/익절/홀딩 전략을 제시합니다.")
        
        if st.button("✨ 내 포트폴리오 전체 진단받기", type="primary", use_container_width=True):
            with st.spinner("AI 매니저가 각 종목별 최적의 대응 전략을 계산 중입니다..."):
                pf_text = ""
                for idx, row in display_df.iterrows():
                    pf_text += f"- {row['종목명']}: 매수단가 {row['매수단가']}, 현재가 {row['현재가']}, 수익률 {row['수익률(%)']:.2f}%\n"
                
                prompt = f"""
                당신은 냉철한 퀀트 투자 리스크 관리자입니다.
                사용자의 현재 포트폴리오 수익률을 바탕으로 각 종목의 '매도/부분매도/홀딩/추가매수' 타점과 이유를 진단하세요.
                최근 시장 동향과 기계적인 손절/익절 라인(예: 수익률 +10% 이상 익절, -5% 이하 기계적 손절 등)을 엄격하게 적용하여 1~2문장으로 조언하세요.
                
                [포트폴리오 현황]
                {pf_text}
                
                [출력 형식] - 반드시 아래 JSON 포맷으로만 응답할 것
                {{
                  "results": [
                    {{"stock": "종목명", "action": "부분매도", "reason": "수익률이 +10%를 초과하여 변동성 대비 절반 익절을 권장합니다."}},
                    {{"stock": "종목명", "action": "홀딩", "reason": "..."}}
                  ]
                }}
                """
                
                try:
                    genai.configure(api_key=gemini_api_key)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    ai_result = json.loads(response.text)
                    
                    st.success("✅ AI 포트폴리오 타점 진단 완료!")
                    for item in ai_result.get("results", []):
                        action_color = "🔴" if "매도" in item["action"] else ("🔵" if "홀딩" in item["action"] else "🟢")
                        st.info(f"**{item['stock']}** 👉 {action_color} **{item['action']}** : {item['reason']}")
                        
                except Exception as e:
                    st.error(f"진단 중 오류 발생: {e}")
                    
        st.write("") # 간격 띄우기
        if st.button("🗑️ 포트폴리오 전체 초기화"):
            st.session_state.portfolio = pd.DataFrame(columns=['종목명', '매수단가', '수량'])
            st.rerun()
    else:
        st.info("아직 등록된 종목이 없습니다. 위 폼에서 매수하신 주식을 추가해 보세요.")