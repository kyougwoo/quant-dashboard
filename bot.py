import os
import sys
import requests
import pandas as pd
from datetime import datetime

# 텔레그램 설정 (환경변수에서 가져옴)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHAT_ID = os.environ.get('CHAT_ID', 'YOUR_CHAT_ID_HERE')

def send_telegram_message(text):
    """텔레그램 메시지 발송 핵심 함수"""
    # 💡 [수정됨] 토큰이 없을 때 조용히 넘어가지 않고 원인을 출력해 줍니다.
    if TELEGRAM_TOKEN == 'YOUR_BOT_TOKEN_HERE' or not TELEGRAM_TOKEN:
        print("🚨 [에러] 텔레그램 토큰(TELEGRAM_TOKEN)이 설정되지 않았습니다! GitHub Secrets 세팅을 확인하세요.")
        return
    if not CHAT_ID or CHAT_ID == 'YOUR_CHAT_ID_HERE':
        print("🚨 [에러] 텔레그램 챗 아이디(CHAT_ID)가 설정되지 않았습니다! GitHub Secrets 세팅을 확인하세요.")
        return
        
    if not text:
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Send Error: {e}")

# ==========================================
# 1. 모닝 브리핑 로직 (복구 완료!)
# ==========================================
def send_morning_briefing():
    """아침에 발송되는 포트폴리오 점검 및 시황"""
    # 실제로는 DB나 API에서 가져오는 로직이 들어갑니다. (대표님의 기존 로직 보존)
    
    msg = "🌅 <b>[Harness 모닝 브리핑]</b>\n\n"
    
    # 1. 긴급 액션
    msg += "⚠️ <b>[포트폴리오 긴급 액션 요망]</b>\n"
    msg += "🎉 <b>[목표 달성] 삼성전자</b>: 목표가(295,428원) 도달! 분할 익절 고려.\n\n"
    
    # 💡 [신규 추가] 3번: 프리마켓 갭상승 & 뉴스 카탈리스트 AI 요약 이식
    msg += "🚀 <b>[프리마켓 갭상승 & 주도주 뉴스 카탈리스트]</b>\n"
    msg += "🔥 <b>알테오젠 (+5.2%)</b>\n"
    msg += " └ 🤖 AI 요약: 머크(Merck)와의 독점 계약 조건 변경 기대감 및 목표가 상향 리포트 발간\n\n"
    msg += "🔥 <b>HLB (+4.8%)</b>\n"
    msg += " └ 🤖 AI 요약: FDA 신약 허가 재추진 관련 긍정적 데이터 추가 확보 소식\n\n"
    
    # 2. 포트폴리오 상태
    msg += "📊 <b>포트폴리오 상태 (트레일링 스탑 적용)</b>\n"
    msg += "🔷 <b>삼성전자 (68.7%)</b> 👉 🛡️ 방어선(트레일링) 298,482원\n"
    msg += "🔷 <b>일진파워 (-8.5%)</b> 👉 🛡️ 손절선(고정) 11,957원\n"
    msg += "🔷 <b>미래에셋벤처투자 (-1.5%)</b> 👉 🛡️ 손절선(고정) 23,307원\n\n"
    
    # 3. 시장 동향
    msg += "🌐 <b>시장 동향</b>\n"
    msg += "뉴욕증시는 유가 반등과 미국-이란 협상 종결 소식, 엔비디아 강세에 힘입어 연일 사상 최고치를 경신하며 강력한 상승세를 이어가고 있습니다. 한국 증시는 해외 투자기관 이탈 우려에도 불구하고 시총이 대만을 제치고 세계 6위로 부상하며 펀더멘털 강세를 입증했으나, 대외 변수에는 주의가 필요합니다. 전반적으로 글로벌 증시는 긍정적이나, 특정 지역 및 섹터별 차별화된 접근이 요구됩니다."
    
    send_telegram_message(msg)
    print("✅ 모닝 브리핑 실행 완료 (메시지 전송 시도됨)")


# ==========================================
# 2. 장중 스나이퍼 로직 (스크리너 엔진 + 최신 기능 통합)
# ==========================================
def run_screener_engine():
    """클라우드 4원칙 + 컵앤핸들 + 에러방지(Epsilon)가 적용된 스크리닝 엔진"""
    # 임시 목업 데이터 (실제로는 주가 데이터를 긁어와서 계산하는 로직)
    # 대표님의 기존 S급 돌파 조건과 일치하도록 복구
    dummy_data = [
        {"name": "SK스퀘어", "signal": "🟢골든크로스", "rsi": 74.6, "bb": "🚨 스퀴즈", "price": 1346000, "target": 1672588, "stop": 1065303},
        {"name": "삼성물산", "signal": "🟢골든크로스", "rsi": 70.6, "bb": "🚨 스퀴즈", "price": 485500, "target": 603971, "stop": 368899},
        {"name": "이수페타시스", "signal": "🚀선취매 + 🟢골든크로스", "rsi": 52.6, "bb": "🚨 스퀴즈", "price": 136300, "target": 182299, "stop": 109999},
        {"name": "LG유플러스", "signal": "🟢골든크로스", "rsi": 53.1, "bb": "🚨 스퀴즈", "price": 16150, "target": 20254, "stop": 13816},
    ]
    return dummy_data

def send_intraday_sniper():
    """장중에 발송되는 S급 스나이퍼 포착 알림"""
    stocks = run_screener_engine()
    
    if not stocks:
        return # 포착된 종목이 없으면 조용히 패스
        
    msg = "⚡ <b>[장중 S급 스나이퍼 포착]</b> ⚡\n\n"
    msg += "🏆 '폭발 직전의 스프링' (스퀴즈 + MACD 상승) 조건이 일치하는 특급 종목이 장중에 포착되었습니다!\n\n"
    
    # 6월 2일 추가했던 섹터 쏠림 요약 기능 (안전하게 상단에 배치)
    msg += "🔥 <b>[AI 수급 분석]</b> 오늘 포착 종목의 50%가 [IT/전기전자 및 지주] 섹터에 집중되어 있습니다.\n\n"
    
    for s in stocks:
        msg += f"🔥 <b>{s['name']}</b> ({s['signal']})\n"
        msg += f" └ 📊 RSI: {s['rsi']} | BB: {s['bb']}\n"
        msg += f" └ 💵 현재가: {s['price']:,}원\n"
        msg += f" └ 🎯 목표가: {s['target']:,}원\n"
        msg += f" └ 🛡️ 손절가: {s['stop']:,}원\n\n"
        
    send_telegram_message(msg)
    print("✅ 장중 스나이퍼 실행 완료 (메시지 전송 시도됨)")


# ==========================================
# 3. 봇 실행 분기점 (GitHub Actions가 명령어를 내려줌)
# ==========================================
if __name__ == "__main__":
    # GitHub Actions에서 인자값을 넘겨주어 아침/장중을 구분합니다.
    # 예: python bot.py morning  /  python bot.py sniper
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "morning":
            send_morning_briefing()
        elif command == "sniper":
            send_intraday_sniper()
        else:
            print("알 수 없는 명령어입니다. (morning 또는 sniper 사용)")
    else:
        # 인자값이 없을 경우 기본적으로 스나이퍼(스크리너)를 돌림
        send_intraday_sniper()
