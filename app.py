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
st.set_page_config(page_title="클라우드 기법 퀀트 대시보드", layout="wide", page_icon="☁️")

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
fast_search = st.sidebar.radio("관심 종목 바로가기", ["직접 입력", "삼성전자", "SK하이닉스", "카카오", "현대차", "아난티", "두산에너빌리티", "HD현대미포", "제주반도체", "루닛", "유니슨", "영풍", "인스코비"])
if fast_search == "직접 입력":
    stock_name = st.sidebar.text_input("분석할 종목명 (또는 6자리 코드)", "삼성전자")
else:
    stock_name = fast_search

# ==========================================
# 2. 데이터 수집 & 클라우드 기법 파이썬 수식화 ⭐
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
        
    # 속도 최적화를 위한 40여개 주요 종목 하이패스 매핑
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
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        news_list = [item.title.text for item in items[:5] if item.title]
        return news_list if news_list else ["최신 관련 뉴스를 찾지 못했습니다."]
    except Exception as e:
        return [f"뉴스 수집 중 오류 발생: {e}"]

def calculate_cloud_indicators(df):
    """클라우드 주식 기법 (지수이평선, 거래량 기준선, 터틀 ATR) 계산"""
    if df is None or len(df) < 200: return df, {}
    
    # 1. 지수 이동평균선 (EMA 5, 15, 50, 200) - 글로벌/클라우드 기준
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # 2. 대량 거래량 터진 날의 종가 (지지/저항 매물대)
    recent_60_df = df.tail(60)
    max_vol_idx = recent_60_df['Volume'].idxmax()
    vol_ref_price = recent_60_df.loc[max_vol_idx, 'Close']
    df['Vol_Ref_Price'] = vol_ref_price
    
    # 3. 터틀 트레이딩 ATR (14일 진짜 평균 변동폭) 계산
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    # 최근 데이터 추출
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 클라우드 기법 5원칙 체크리스트 로직
    is_above_200 = latest['Close'] > latest['EMA200']
    is_ema_uptrend = latest['EMA200'] >= prev['EMA200']
    is_golden_cross = (prev['EMA5'] <= prev['EMA15']) and (latest['EMA5'] > latest['EMA15'])
    is_above_vol_ref = latest['Close'] > latest['Vol_Ref_Price']
    
    indicators = {
        "EMA5": latest['EMA5'], "EMA15": latest['EMA15'], "EMA200": latest['EMA200'],
        "Vol_Ref_Price": vol_ref_price,
        "ATR": latest['ATR'],
        "Cloud_Rules": {
            "주가 > 200일선": is_above_200,
            "200일선 우상향": is_ema_uptrend,
            "5일선 15일선 돌파(골든크로스)": is_golden_cross or (latest['EMA5'] > latest['EMA15']),
            "최대 거래량 종가 돌파": is_above_vol_ref
        }
    }
    return df, indicators

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
st.title("☁️ 클라우드 기법 AI 퀀트 대시보드")
st.markdown("강의 핵심 원리 **(EMA 5/15/200, 거래량 매물대 돌파, 터틀 ATR 손절)**가 완벽히 적용된 3-Agent 시스템")

tab1, tab2, tab3 = st.tabs(["📊 개별 종목 분석", "💼 내 포트폴리오 관리", "🔍 클라우드 조건 검색기 (Screener)"])

# ------------------------------------------
# [탭 1] 개별 종목 분석
# ------------------------------------------
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
        start_date = end_date - timedelta(days=365) # 200일선 계산을 위해 1년치 로드
        with st.spinner("주가 및 지수이평선(EMA) 계산 중..."):
            try: 
                raw_df = fdr.DataReader(ticker, start_date, end_date)
                df, tech_ind = calculate_cloud_indicators(raw_df)
            except Exception: df = None; tech_ind = {}
            
        if df is not None and not df.empty:
            display_df = df.tail(90)
            fig = go.Figure(data=[go.Candlestick(x=display_df.index, open=display_df['Open'], high=display_df['High'], low=display_df['Low'], close=display_df['Close'], name="주가")])
            # 클라우드 주요 이평선 및 거래량 기준선 추가
            fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA5'], mode='lines', line=dict(color='magenta', width=1.5), name='5 EMA'))
            fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA15'], mode='lines', line=dict(color='yellow', width=1.5), name='15 EMA'))
            fig.add_trace(go.Scatter(x=display_df.index, y=display_df['EMA200'], mode='lines', line=dict(color='black', width=2.5, dash='dot'), name='200 EMA'))
            fig.add_trace(go.Scatter(x=display_df.index, y=display_df['Vol_Ref_Price'], mode='lines', line=dict(color='red', width=2, dash='dash'), name='최대 거래량 종가 (매물대)'))
            
            fig.update_layout(title="최근 3개월 캔들 및 클라우드 지표 (5/15/200 EMA)", xaxis_rangeslider_visible=False, height=450, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**☁️ 클라우드 기법 매수 4원칙 체크**")
        if tech_ind:
            rules = tech_ind["Cloud_Rules"]
            for rule, passed in rules.items():
                icon = "✅" if passed else "❌"
                st.write(f"{icon} {rule}")
            
            atr_val = int(tech_ind.get('ATR', 0))
            current_p = int(df['Close'].iloc[-1])
            stop_loss = current_p - (atr_val * 2)
            st.info(f"🛡️ **터틀 스탑(손절가):** {stop_loss:,}원\n*(현재가 - ATR×2 적용)*")
        
        st.markdown("**📰 최근 뉴스 헤드라인**")
        news_items = get_recent_news(actual_name)
        for i, news in enumerate(news_items[:3]): st.caption(f"{i+1}. {news}")

    # AI 분석 실행
    st.markdown("---")
    if df is not None and not df.empty:
        if st.button("🚀 클라우드 기법 3-Agent 분석 실행", type="primary", use_container_width=True):
            with st.spinner("클라우드 기법(매물대 돌파, 이평선 정배열)을 기반으로 타점을 계산 중입니다..."):
                recent_close = int(df['Close'].iloc[-1])
                passed_rules_count = sum(1 for v in rules.values() if v)
                
                # 클라우드 기법 맞춤형 프롬프트
                prompt = f"""
                당신은 '클라우드 주식 기법'을 마스터한 월스트리트 상위 1% 퀀트 트레이더입니다.
                아래 데이터를 바탕으로 종목을 분석하세요.

                [분석 팩트 데이터]
                - 종목명: {actual_name} (현재가: {recent_close}원)
                - 클라우드 4원칙 통과 개수: 4개 중 {passed_rules_count}개 통과 (주가>200EMA, EMA5>15돌파, 대량거래량 종가 돌파 여부 종합)
                - 터틀 트레이딩 권장 손절선: {stop_loss}원 (2*ATR 적용)
                - 최신 뉴스 동향: {news_items}

                [에이전트 규칙]
                1. technicalAgent: '클라우드 4원칙 통과 개수'를 절대 기준으로 삼으세요. 통과 개수가 많으면 상방(매수) 점수를 높게 주고, 200일선 아래거나 거래량 매물대를 못 뚫었으면 부정적으로 평가하세요. (-10~10점)
                2. fundamentalAgent: 뉴스의 단기적 호재/악재 스코어(-10~10) 도출.
                3. riskManager: 위 의견 취합. '터틀 트레이딩 손절선({stop_loss}원)'을 반드시 언급하며, 기대수익과 손절폭을 비교하여 최종 포지션(적극매수/분할매수/관망/매도)을 결정하세요.

                [출력 형식 - 순수 JSON만]
                {{"technicalAgent": {{"score": 8, "reasoning": "200일선 위에 안착했으며 대량 거래량 종가를 돌파하여 상승 추세가 확고합니다."}}, "fundamentalAgent": {{"score": 6, "reasoning": "..."}}, "riskManager": {{"action": "분할매수", "positionSize": "20%", "reasoning": "터틀 스탑 기준 ...원을 손절선으로 잡고..."}}}}
                """
                
                try:
                    result = get_ai_analysis(prompt, gemini_api_key)
                    st.success("✅ 클라우드 기법 기반 AI 분석 완료!")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("### 📈 차트 분석가")
                        st.metric("기술적 모멘텀", f"{result['technicalAgent']['score']}점")
                        st.write(result['technicalAgent']['reasoning'])
                    with c2:
                        st.markdown("### 📰 기본적 분석가")
                        st.metric("펀더멘털 / 뉴스", f"{result['fundamentalAgent']['score']}점")
                        st.write(result['fundamentalAgent']['reasoning'])
                    with c3:
                        st.markdown("### 🛡️ 리스크 관리자")
                        action_color = "🔴" if "매수" in result['riskManager']['action'] else ("🔵" if "매도" in result['riskManager']['action'] else "⚪")
                        st.metric(f"최종 타점 {action_color}", f"{result['riskManager']['action']}")
                        st.markdown(f"**진입 비중:** `{result['riskManager']['positionSize']}`")
                        st.write(result['riskManager']['reasoning'])
                except Exception as e:
                    st.error(f"오류 발생: {e}")

# ------------------------------------------
# [탭 2] 내 포트폴리오 관리 (업그레이드됨: 클라우드 진단 연동) ⭐
# ------------------------------------------
with tab2:
    st.subheader("💼 현재 보유 종목 관리 및 AI 타점 진단")
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
            st.success(f"'{display_name}' 추가 완료!")

    if not st.session_state.portfolio.empty:
        display_df = st.session_state.portfolio.copy()
        current_prices = []; profits = []; profit_rates = []
        
        for idx, row in display_df.iterrows():
            actual_n, tck = get_stock_info(row['종목명'])
            cur_p = get_current_price(tck) if tck else 0
            buy_total = row['매수단가'] * row['수량']
            cur_total = cur_p * row['수량']
            profit = cur_total - buy_total
            rate = (profit / buy_total * 100) if buy_total > 0 else 0
            current_prices.append(cur_p); profits.append(profit); profit_rates.append(rate)
            
        display_df['현재가'] = current_prices; display_df['수익금'] = profits; display_df['수익률(%)'] = profit_rates
        
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
            if (st.session_state.portfolio.iloc[i]['매수단가'] != edited_df.iloc[i]['매수단가'] or st.session_state.portfolio.iloc[i]['수량'] != edited_df.iloc[i]['수량']):
                has_changed = True; break
        if has_changed:
            st.session_state.portfolio['매수단가'] = edited_df['매수단가']; st.session_state.portfolio['수량'] = edited_df['수량']
            st.rerun()

        col_del1, col_del2 = st.columns([3, 1])
        with col_del1: del_target = st.selectbox("삭제할 종목 선택", ["선택 안함"] + display_df['종목명'].tolist(), label_visibility="collapsed")
        with col_del2:
            if st.button("❌ 삭제", use_container_width=True) and del_target != "선택 안함":
                st.session_state.portfolio = st.session_state.portfolio[st.session_state.portfolio['종목명'] != del_target]; st.rerun()

        st.markdown("---")
        st.markdown("### 🤖 보유 종목 클라우드 타점 진단 (승률 기반)")
        if st.button("✨ 내 포트폴리오 전체 진단받기", type="primary", use_container_width=True):
            with st.spinner("클라우드 기법(터틀 손절선, 200일선 등)을 적용하여 포트폴리오 최적 대응 전략을 계산 중입니다..."):
                pf_text = ""
                for idx, row in display_df.iterrows():
                    actual_n, tck = get_stock_info(row['종목명'])
                    
                    # 💡 추가: 각 포트폴리오 종목마다 클라우드 지표 즉석 계산
                    tech_status = "지표 계산 불가"
                    if tck:
                        try:
                            temp_df = fdr.DataReader(tck, datetime.today() - timedelta(days=365), datetime.today())
                            calc_df, ind = calculate_cloud_indicators(temp_df)
                            if ind:
                                rules = ind["Cloud_Rules"]
                                atr_val = int(ind.get('ATR', 0))
                                current_p = int(calc_df['Close'].iloc[-1])
                                stop_loss = current_p - (atr_val * 2)
                                
                                tech_status = f"200일선 위({'O' if rules['주가 > 200일선'] else 'X'}), 5/15일선 정배열({'O' if rules['5일선 15일선 돌파(골든크로스)'] else 'X'}), 터틀손절가({stop_loss:,}원)"
                        except:
                            pass
                            
                    pf_text += f"- {row['종목명']}: 매수단가 {row['매수단가']}, 현재가 {row['현재가']}, 수익률 {row['수익률(%)']:.2f}%, [기술적 상태: {tech_status}]\n"
                
                # 💡 업그레이드: 클라우드 기법이 반영된 진단 프롬프트
                prompt = f"""
                당신은 '클라우드 주식 기법'을 마스터한 냉철한 퀀트 투자 리스크 관리자입니다.
                사용자의 현재 포트폴리오 수익률과 '기술적 상태(클라우드 지표 및 터틀 손절선)'를 종합하여 각 종목의 '전량매도/부분매도/홀딩/추가매수' 타점과 이유를 진단하세요.
                
                [진단 엄격 원칙]
                1. 수익률이 크게 났더라도 터틀 손절가를 이탈했거나 200일선 아래로 꺾인 경우 기계적인 손절/비중 축소를 강력히 경고하세요.
                2. 기술적 상태가 정배열(O)이며 200일선 위라면 수익을 길게 끌고가는 홀딩/추가매수 의견을 낼 수 있습니다.
                3. 감정을 배제하고 냉정하게 1~2문장으로 조언하세요.
                
                [포트폴리오 현황]
                {pf_text}
                
                [출력 형식 - 반드시 아래 JSON 포맷으로만 응답]
                {{
                  "results": [
                    {{"stock": "종목명", "action": "부분매도", "reason": "수익률 10% 도달 및 5/15일선 역배열 전환 우려로 절반 익절을 권장합니다."}},
                    {{"stock": "종목명", "action": "전량매도", "reason": "현재가가 터틀 손절가를 이탈하였으므로 원칙에 따라 즉시 전량 매도해야 합니다."}}
                  ]
                }}
                """
                try:
                    genai.configure(api_key=gemini_api_key)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    ai_result = json.loads(response.text)
                    st.success("✅ 포트폴리오 클라우드 타점 진단 완료!")
                    for item in ai_result.get("results", []):
                        action_color = "🔴" if "매도" in item["action"] else ("🔵" if "홀딩" in item["action"] else "🟢")
                        st.info(f"**{item['stock']}** 👉 {action_color} **{item['action']}** : {item['reason']}")
                except Exception as e: st.error(f"오류 발생: {e}")

# ------------------------------------------
# [탭 3] 클라우드 조건 검색기 (신규!) ⭐
# ------------------------------------------
with tab3:
    st.subheader("🔍 클라우드 매수 급소 스크리너")
    st.markdown("""
    강의에서 언급된 **가장 폭발적인 상승 초입 구간(정배열 초입, 200일선 돌파, 대량거래 돌파)**을 
    주요 종목 풀(Pool)에서 자동으로 찾아냅니다. (속도를 위해 주요 우량주 40여 개 스캔)
    """)
    
    if st.button("🔎 조건 검색 실행", type="primary"):
        search_list = {
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
            "제주반도체": "080220", "루닛": "328130", "유니슨": "018000", 
            "영풍": "000670", "인스코비": "006490"
        }
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, (name, code) in enumerate(search_list.items()):
            status_text.text(f"스캔 중... {name} ({i+1}/{len(search_list)})")
            try:
                # 200일선 계산을 위해 1년치 데이터 가져오기
                temp_df = fdr.DataReader(code, datetime.today() - timedelta(days=365), datetime.today())
                calc_df, ind = calculate_cloud_indicators(temp_df)
                
                if ind:
                    rules = ind["Cloud_Rules"]
                    score = sum(1 for v in rules.values() if v)
                    
                    # 4원칙 중 2개 이상 통과한 종목만 필터링
                    if score >= 2:
                        results.append({
                            "종목명": name,
                            "통과 개수": f"{score}/4",
                            "주가 > 200일선": "✅" if rules["주가 > 200일선"] else "❌",
                            "5/15일선 정배열": "✅" if rules["5일선 15일선 돌파(골든크로스)"] else "❌",
                            "대량거래 돌파": "✅" if rules["최대 거래량 종가 돌파"] else "❌",
                            "현재가": f"{int(calc_df['Close'].iloc[-1]):,}원",
                            "터틀 손절가": f"{int(calc_df['Close'].iloc[-1] - (ind['ATR']*2)):,}원"
                        })
            except Exception:
                pass
            progress_bar.progress((i + 1) / len(search_list))
            
        status_text.text("✅ 스캔 완료!")
        
        if results:
            st.success(f"조건에 맞는 유망 종목 {len(results)}개를 발견했습니다!")
            res_df = pd.DataFrame(results)
            st.dataframe(res_df, use_container_width=True, hide_index=True)
        else:
            st.warning("현재 시장에서 클라우드 4원칙을 2개 이상 통과한 종목이 없습니다. (하락장 가능성)")
