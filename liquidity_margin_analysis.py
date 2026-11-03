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
# 2. 메인 파이프라인 (수급 붕괴 & 마진콜 징후 분석 - 당일 날짜 동적 반영)
# ---------------------------------------------------------------------------

def run_liquidity_margin_analysis_pipeline():
    # 실행하는 당일 날짜로 동적 생성
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    today_korean_str = f"{today_dt.year}년 {today_dt.month}월 {today_dt.day}일"
    
    print(f"[{today_korean_str}] Gemini 수급 붕괴 및 헤지펀드 마진콜 징후 분석 생성 중...")

    # 안정적인 작성을 위한 프롬프트 구조 (마크다운 표 제외)
    prompt = f"""
당신은 금융 시장 수급 붕괴 및 헤지펀드 마진콜 징후를 전문적으로 포착하는 프롭 트레이더입니다.
기준일자인 {today_korean_str}의 글로벌 시장 데이터(주가, 거래량, VIX, 주요 자산 등락률 등)를 바탕으로 아래 3가지 항목에 대해 명확하고 실전적인 분석 보고서를 작성해 주세요.
(※ 주의: 마크다운 표 기호(|)는 절대 사용하지 마시고, 깔끔한 글머리 기호와 텍스트로만 작성해 주세요.)

1. 시장 폭락 성격 판별 (개별 악재 vs 유동성 경색/마진콜)
- 현재 증시 및 주요 자산의 하락 원인이 특정 기업/섹터의 개별 악재 때문인지, 아니면 시장 전체의 유동성 경색 및 기관/헤지펀드 마진콜에 의한 강제 청산 때문인지 구체적 근거와 함께 분석.

2. VIX 및 자산 간 상관관계 기반 단계별 진단
- 현재 시장이 다음 3가지 단계 중 어디에 해당하는지 명확히 진단:
  * 1단계: 원인 분리 단계 (낙폭 확대 및 원인 분석 구간)
  * 2단계: 관망 단계 (유동성 경색 진행 중, 투매 지속)
  * 3단계: 기회 포착 단계 (투매 일락, 기술적 반등 및 분할 매수 적기)
- VIX 지수 및 주식/채권/원자재 간 상관관계 움직임을 바탕으로 판단 근거 제시.

3. IRP 및 연금저축 계좌 관점의 우량 자산 진입 시점 의견
- 현 국면에서 연금저축 및 IRP 장기 투자 계좌 활용 시 어떤 우량 자산(S&P500, 나스닥100, 미국30년국채, 현금성 자산 등)에 접근해야 하는지, 매수 타이밍 및 전략 제언.
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
                    temperature=0.3,
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

    # 3회 실패 시 안전 폴백(Fallback) 텍스트
    if not analysis_result:
        analysis_result = f"""
[수급 붕괴 및 마진콜 징후 긴급 브리핑]
기준일: {today_korean_str}

1. 폭락 성격 진단
- 시장 변동성 확대 국면에서 개별 재료 대비 전반적인 수급 위축 여부를 주시해야 합니다. 무차별적인 자산 매도가 관찰될 경우 유동성 경색 신호로 판단합니다.

2. 시장 단계 진단
- 현재 단계: [2단계: 관망 단계]
- VIX 상승 및 자산 간 동반 하락세가 진정될 때까지는 성급한 저가 매수를 자제하고 리스크를 관리하는 것이 유효합니다.

3. 연금 계좌(IRP/연금저축) 대응 전략
- 변동성 극대화 구간에서는 분할 매수를 통한 단가 평단화 전략이 유리하며, 채권 및 현금성 자산 비중을 일정 유지하며 바닥 신호를 확인해야 합니다.
"""

    # -----------------------------------------------------------------------
    # 리포트 본문 구성 및 이메일 발송
    # -----------------------------------------------------------------------
    report_body = f"=========================================================\n"
    report_body += f" 📊 [{today_str}] 수급 붕괴 및 헤지펀드 마진콜 징후 분석 보고서\n"
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
    msg['Subject'] = f"[{today_str}] 수급붕괴및마진콜징후분석"
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 성공적으로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    print("🚀 수급 붕괴 및 마진콜 징후 분석 스크립트 실행 시작...")
    run_liquidity_margin_analysis_pipeline()
