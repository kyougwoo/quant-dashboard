import os
import time
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import FinanceDataReader as fdr
import logging

# 시스템 로그
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 1. 환경 변수 세팅 (GitHub Secrets에서 안전하게 가져옴) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(text):
    """텔레그램 메시지 발송 함수"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        if res.status_code == 200:
            print("✅ 텔레그램 전송 성공!")
            return True
        else:
            print(f"🚨 텔레그램 전송 실패: {res.text}")
            return False
    except Exception as e:
        print(f"🚨 텔레그램 전송 에러: {e}")
        return False

# --- 2. 스마트 섹터 맵 (app.py와 동일한 강력한 분류 엔진) ---
def get_sector_map():
    # 💡 [분류 엔진 강화] 코스피/코스닥 주요 대장주 및 헷갈리기 쉬운 종목 집중 하드코딩
    sector_dict = {
        '삼성물산': '지주/복합기업', 'SK': '지주/복합기업', 'LG': '지주/복합기업', 'CJ': '지주/복합기업', '두산': '지주/복합기업', '한화': '지주/복합기업', 'LS': '지주/복합기업', 'HD현대': '지주/복합기업',
        '삼성전자': 'IT/반도체', 'SK하이닉스': 'IT/반도체', '한미반도체': 'IT/반도체', '리노공업': 'IT/반도체', 'HPSP': 'IT/반도체', 'ISC': 'IT/반도체', '이수페타시스': 'IT/전기전자', 'HD현대일렉트릭': 'IT/전기전자', 'LS ELECTRIC': 'IT/전기전자',
        '현대차': '자동차/모빌리티', '기아': '자동차/모빌리티', '현대모비스': '자동차/모빌리티', 'HL만도': '자동차/모빌리티', '현대위아': '자동차/모빌리티',
        'LG에너지솔루션': '화학/2차전지', '에코프로비엠': '화학/2차전지', '에코프로': '화학/2차전지', '에코프로머티': '화학/2차전지', 'POSCO홀딩스': '화학/2차전지', '엘앤에프': '화학/2차전지', '포스코퓨처엠': '화학/2차전지', 'LG화학': '화학/2차전지', '엔켐': '화학/2차전지', '금양': '화학/2차전지',
        '삼성바이오로직스': '바이오/헬스케어', '셀트리온': '바이오/헬스케어', '알테오젠': '바이오/헬스케어', 'HLB': '바이오/헬스케어', '삼천당제약': '바이오/헬스케어', '유한양행': '바이오/헬스케어', '리가켐바이오': '바이오/헬스케어', '휴젤': '바이오/헬스케어', '루닛': '바이오/헬스케어',
        'NAVER': 'SW/인터넷', '카카오': 'SW/인터넷', '엔씨소프트': 'SW/인터넷', '크래프톤': 'SW/인터넷', '펄어비스': 'SW/인터넷', '카카오페이': 'SW/인터넷',
        'KB금융': '금융', '신한지주': '금융', '하나금융지주': '금융', '메리츠금융지주': '금융', '삼성생명': '금융', '삼성화재': '금융', '카카오뱅크': '금융', '기업은행': '금융', '우리금융지주': '금융',
        'HD현대중공업': '기계/조선/방산', '한화오션': '기계/조선/방산', '삼성중공업': '기계/조선/방산', '한화에어로스페이스': '기계/조선/방산', 'LIG넥스원': '기계/조선/방산', '현대로템': '기계/조선/방산',
        '하이브': '엔터/미디어', 'JYP Ent.': '엔터/미디어', '에스엠': '엔터/미디어', '와이지엔터테인먼트': '엔터/미디어', 'CJ ENM': '엔터/미디어',
        '대한항공': '물류/운송', 'HMM': '물류/운송', '현대건설': '건설/부동산', 'GS건설': '건설/부동산', '한국전력': '유틸리티/에너지', '한국가스공사': '유틸리티/에너지', '두산에너빌리티': '유틸리티/에너지'
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
                    elif any(k in s for k in ['반도체', '전자부품', '컴퓨터', '통신', '방송', '디스플레이', '기기', '장비', '전기']): sector_dict[n] = 'IT/반도체'
                    elif any(k in s for k in ['소프트웨어', '정보 서비스', '자료처리', '포털', '출판', 'IT']): sector_dict[n] = 'SW/인터넷'
                    elif any(k in s for k in ['자동차', '모터', '운송장비', '엔진', '항공기']): sector_dict[n] = '자동차/모빌리티'
                    elif any(k in s for k in ['의약품', '의료', '보건', '생물', '약', '진단']): sector_dict[n] = '바이오/헬스케어'
                    elif any(k in s for k in ['금융', '보험', '은행', '신탁', '투자', '증권', '카드']): sector_dict[n] = '금융'
                    elif any(k in s for k in ['지주']): sector_dict[n] = '지주/복합기업'
                    elif any(k in s for k in ['화학', '플라스틱', '고무', '전지', '이차전지', '기초 화학', '소재']): sector_dict[n] = '화학/2차전지'
                    elif any(k in s for k in ['금속', '철강', '비금속']): sector_dict[n] = '철강/금속'
                    elif any(k in s for k in ['건설', '토목', '부동산']): sector_dict[n] = '건설/부동산'
                    elif any(k in s for k in ['유통', '도매', '소매', '쇼핑', '음식료', '식료품', '섬유', '의복', '식품', '화장품']): sector_dict[n] = '유통/소비재'
                    elif any(k in s for k in ['엔터', '영화', '방송', '게임', '오디오', '영상', '오락', '레저', '여행']): sector_dict[n] = '엔터/미디어'
                    elif any(k in s for k in ['운송', '항공', '해운', '창고', '여객', '물류']): sector_dict[n] = '물류/운송'
                    elif any(k in s for k in ['전기', '가스', '수도', '에너지', '전력', '원력']): sector_dict[n] = '유틸리티/에너지'
                    elif any(k in s for k in ['기계', '조선', '방산', '무기']): sector_dict[n] = '기계/조선/방산'
                    else: sector_dict[n] = '제조/기타산업'
    except Exception as e: 
        logging.warning(f"Sector map fetch error: {e}")
    return sector_dict

# --- 3. 핵심 로직: 지표 계산 (app.py와 완벽 동기화) ---
def calculate_cloud_indicators(df):
    if df is None or df.empty or len(df) < 200: return None, {}
    df = df[~df.index.duplicated(keep='first')].dropna(subset=['Close'])
    
    try:
        df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA15'] = df['Close'].ewm(span=15, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        epsilon = 1e-9 # 💡 Epsilon 에러 방어 완벽 적용
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
        
        # 💡 컵 앤 핸들 패턴 감지
        is_cup_and_handle = False
        try:
            if len(df) >= 60:
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
        except: pass
        
        latest, prev, prev2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        try: current_monthly_ema10 = float((df['Close'].resample('ME').last() if hasattr(df['Close'].resample('ME'), 'last') else df['Close'].resample('M').last()).ewm(span=10, adjust=False).mean().iloc[-1])
        except: current_monthly_ema10 = float(df['EMA200'].iloc[-1])
        
        indicators = {
            "EMA5": float(latest['EMA5']), "EMA15": float(latest['EMA15']), "EMA200": float(latest['EMA200']), 
            "ATR": float(latest['ATR']) if not pd.isna(latest['ATR']) else float(latest['Close']*0.05),
            "BB_Is_Squeeze": bool(latest['BB_Width'] < df['BB_Width'].tail(20).mean() * 0.8),
            "Monthly_EMA10": current_monthly_ema10, "Is_Above_Monthly_EMA10": bool(latest['Close'] > current_monthly_ema10),
            "RSI": float(latest['RSI']), "MACD_Cross": bool(latest['MACD'] > latest['MACD_Signal']),
            "MACD_Early_Entry": (prev['MACD_Hist'] < 0) and (latest['MACD_Hist'] > prev['MACD_Hist']) and (prev['MACD_Hist'] > prev2['MACD_Hist']),
            "RSI_Turnaround": (prev['RSI'] <= 40) and (latest['RSI'] > prev['RSI']),
            "Cup_and_Handle": is_cup_and_handle,
            "Cloud_Rules": {"주가 > 200일선": bool(latest['Close'] > latest['EMA200']), "200일선 우상향": bool(latest['EMA200'] >= prev['EMA200']), "5/15일선 정배열(돌파)": bool(prev['EMA5'] <= prev['EMA15'] and latest['EMA5'] > latest['EMA15']) or bool(latest['EMA5'] > latest['EMA15'])}
        }
        return df, indicators
    except Exception as e:
        print(f"Indicator calculation error: {e}")
        return None, {}

def get_market_top_stocks():
    """코스피/코스닥 시총 상위 각 150개 추출 (서버 부하 방지용)"""
    try:
        kospi = fdr.StockListing('KOSPI')
        kospi = kospi[~kospi['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        
        kosdaq = fdr.StockListing('KOSDAQ')
        kosdaq = kosdaq[~kosdaq['Name'].str.contains('스팩|제[0-9]+호|ETN|ETF|KODEX|TIGER|KINDEX|KBSTAR', na=False)]
        
        target_stocks = dict(zip(kospi.head(150)['Name'], kospi.head(150)['Code']))
        target_stocks.update(dict(zip(kosdaq.head(150)['Name'], kosdaq.head(150)['Code'])))
        return target_stocks
    except Exception as e:
        print(f"리스트 로드 실패: {e}")
        return {"삼성전자":"005930", "SK하이닉스":"000660"}

# --- 4. 메인 자동화 스캐너 로직 ---
def run_scanner():
    print("🚀 [클라우드 퀀트 무인 봇] 스크리닝을 시작합니다...")
    stocks = get_market_top_stocks()
    sector_map = get_sector_map()
    res = []
    
    total = len(stocks)
    for i, (name, code) in enumerate(stocks.items()):
        try:
            df = fdr.DataReader(code, (datetime.today()-timedelta(days=700)).strftime('%Y-%m-%d'), datetime.today().strftime('%Y-%m-%d'))
            df, ind = calculate_cloud_indicators(df)
            
            if ind:
                sc = sum(1 for v in ind["Cloud_Rules"].values() if v)
                
                if sc >= 2 and ind.get("Is_Above_Monthly_EMA10"):
                    curr_p = float(df['Close'].iloc[-1])
                    entry1 = ind['EMA5'] if curr_p > ind['EMA5'] else curr_p
                    a = ind['ATR']
                    
                    tags = []
                    if ind.get('Cup_and_Handle'): tags.append("☕컵앤핸들")
                    if ind['MACD_Early_Entry']: tags.append("🚀선취매")
                    if ind['RSI_Turnaround']: tags.append("📉RSI턴")
                    if ind['MACD_Cross']: tags.append("🟢골든크로스")
                    if ind['BB_Is_Squeeze']: tags.append("🚨스퀴즈")
                    
                    if tags:
                        res.append({
                            "name": name,
                            "sector": sector_map.get(name, "기타분류"),
                            "price": curr_p,
                            "entry": entry1,
                            "target": entry1 + (a*4),
                            "stop": entry1 - (a*2),
                            "tags": " + ".join(tags)
                        })
        except Exception as e:
            pass 
        
        if (i+1) % 50 == 0:
            print(f"진행 상황: {i+1} / {total} 스캔 완료...")
            
    print(f"✅ 스캔 완료. 총 {len(res)}개 특급 타점 발견!")
    
    # 💡 텔레그램 메시지 조립 (테마 쏠림 감지 엔진 포함)
    if res:
        df_res = pd.DataFrame(res)
        msg = f"🚨 <b>[Harness 무인 스캐너 포착]</b>\n"
        msg += f"오늘 장 마감 전, VVIP 타점에 진입한 특급 종목 {len(res)}개를 발견했습니다!\n\n"
        
        # 💡 [핵심 버그 수정] '기타분류', '제조/기타산업'은 제외하고 의미있는 1등 테마 찾기
        if not df_res.empty and 'sector' in df_res.columns:
            meaningful_df = df_res[~df_res['sector'].isin(['기타분류', '제조/기타산업'])]
            if not meaningful_df.empty:
                sector_counts = meaningful_df['sector'].value_counts()
                if not sector_counts.empty:
                    top_sector = sector_counts.index[0]
                    top_count = sector_counts.iloc[0]
                    if top_count >= 2:
                        msg += f"🔥 <b>[AI 수급 쏠림 감지]</b>\n"
                        msg += f"포착된 종목 중 {top_count}개가 <b>[{top_sector}]</b> 섹터입니다. 메이저 수급 유입이 의심되니 해당 섹터 관련주를 1순위로 확인하세요!\n\n"
                        msg += "-----------------------------------\n\n"
        
        for r in res:
            msg += f"🎯 <b>{r['name']}</b> ({r['tags']})\n"
            msg += f" └ 💵 현재가: {int(r['price']):,}원\n"
            msg += f" └ 📥 1차매수(대기): {int(r['entry']):,}원\n"
            msg += f" └ 🏁 목표가: {int(r['target']):,} / 🛡️ 손절: {int(r['stop']):,}\n\n"
        
        msg += "자세한 차트 분석은 클라우드 퀀트 PRO 대시보드에서 확인하세요!"
        
        # 길이가 너무 길면 분할 전송 (안전 장치)
        if len(msg) > 3800:
            chunks = [msg[i:i+3800] for i in range(0, len(msg), 3800)]
            for chunk in chunks:
                send_telegram(chunk)
                time.sleep(1)
        else:
            send_telegram(msg)
    else:
        send_telegram("💡 <b>[Harness 무인 스캐너]</b>\n오늘 장에는 안전한 S급 타점(월봉 10선 위) 종목이 없습니다. 현금 비중을 유지하며 관망하세요.")

if __name__ == "__main__":
    run_scanner()
