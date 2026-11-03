import os
import time
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. 환경 및 사용자 설정 (GitHub Secrets / 환경변수에서 불러옴)
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# 2. 메인 파이프라인 (실행 당일 날짜 동적 생성 반영)
# ---------------------------------------------------------------------------

def run_market_risk_analysis_pipeline():
    # 실행하는 당일 날짜로 동적 생성
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    today_korean_str = f"{today_dt.year}년 {today_dt.month}월 {today_dt.day}일"
    
    print(f"[{today_korean_str}] Gemini 시장 하락세 및 리스크 정밀 진단 생성 중...")

    # 프롬프트 구성
    prompt = f"""
당신은 신영증권 김효진 박사의 버블 고점 시그널 분석 방법론을 활용하는 금융 시장 위험 평가 전문가입니다.
기준일자인 {today_korean_str}을 바탕으로 아래 2가지 주제에 대해 한국어로 명확하고 전문적인 애널리스트 톤의 리포트를 작성해 주세요. 
(※ 주의: 마크다운 표 기호(|)는 절대 사용하지 마세요.)

1. 글로벌 증시 계단식 하락 및 금리 표면장력 압박
- 미국 나스닥, 다우, S&P 500의 최근 흐름 비교
- 유럽, 대만, 한국 등 글로벌 테크 및 주요국 증시 하락 징후 평가
- 미국의 기준금리 방향성과 할인율 압박 분석
- 종합 결론 (안심 단계 / 주의 단계 / 위험 단계 중 택1 및 근거 요약)

2. 시장 상투 및 하락장 징후 6대 지표 감지
- 종합 위험도 평가 (안정 / 주의 / 경계 / 위험 중 택1)
- 6대 핵심 지표별 현황 및 리스크 해석:
  1) 미국 국채 10년물-2년물 금리차
  2) 미국 실질 기준금리
  3) 버핏 지수
  4) 마진 데트 (신용잔고)
  5) 쉴러 PE (CAPE)
  6) 공포와 탐욕 지수 및 VIX
- 투자자를 위한 실전적 자산 배분 가이드라인 제시
"""

    analysis_result = ""
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"API 요청 시도 중... (시도 {attempt}/{max_retries})")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=8192
                )
            )
            
            if response and response.text and len(response.text.strip()) > 0:
                analysis_result = response.text.strip()
                break
            else:
                print(f"[경고] 시도 {attempt}: 응답이 비어 있습니다.")
        except Exception as e:
            print(f"[경고] 시도 {attempt} 실패: {e}")
            
        if attempt < max_retries:
            print("5초 후 재시도합니다...")
            time.sleep(5)

    # 안전 폴백(Fallback) 텍스트
    if not analysis_result:
        analysis_result = f"""
[시장 하락세 및 리스크 진단 기본 브리핑]
기준일: {today_korean_str}

1. 글로벌 증시 및 금리 압박 진단
- 미국 기술주 중심의 쏠림 현상과 글로벌 주요국(유럽, 대만 등)의 연동 하락 여부를 모니터링해야 하는 국면입니다.
- 고금리 장기화에 따른 할인율 압박이 지속되고 있으므로 보수적인 포트폴리오 관리가 필요합니다.

2. 6대 리스크 지표 요약
- 종합 위험도: [주의 / 경계 단계]
- 10Y-2Y 금리차, 실질금리, 버핏지수, 마진데트, 쉴러PE, VIX 등의 지표를 종합할 때, 밸류에이션 부담과 유동성 변화에 대한 경계감을 유지해야 합니다.

3. 투자 행동 가이드라인
- 급격한 추격 매수를 자제하고, 현금 비중을 일정 수준 확보하며 리스크 관리에 집중할 것을 권장합니다.
"""

    # -----------------------------------------------------------------------
    # 리포트 본문 구성 및 이메일 발송
    # -----------------------------------------------------------------------
    report_body = f"=========================================================\n"
    report_body += f" 📊 [{today_str}] 시장 하락세 및 리스크 정밀 진단 보고서\n"
    report_body += f"=========================================================\n\n"
    report_body += analysis_result

    send_email(report_body, today_str)


# ---------------------------------------------------------------------------
# 3. 이메일 발송 함수
# ---------------------------------------------------------------------------

def send_email(content, today_str):
    print("이메일 발송 준비 중...")
    
    if not SENDER_EMAIL or not SENDER_APP_PASSWORD or not RECEIVER_EMAIL:
        print("❌ 이메일 발송 실패: 환경변수를 확인해 주세요.")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[{today_str}] 시장하락세및리스크진단"
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print("✅ 성공적으로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    print("🚀 시장 하락세 및 리스크 진단 스크립트 실행 시작...")
    run_market_risk_analysis_pipeline()
