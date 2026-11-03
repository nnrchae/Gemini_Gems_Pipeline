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
# 2. 메인 파이프라인 (빅테크 CapEx & AWS 매출 분석 - 당일 날짜 동적 반영)
# ---------------------------------------------------------------------------

def run_bigtech_aws_analysis_pipeline():
    # 실행하는 당일 날짜로 동적 생성
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    today_korean_str = f"{today_dt.year}년 {today_dt.month}월 {today_dt.day}일"
    
    print(f"[{today_korean_str}] Gemini 빅테크 CapEx 및 AWS 매출 추적 분석 생성 중...")

    # 마크다운 표(|) 기호 제외 및 안전한 텍스트 리스트 구조 적용
    prompt = f"""
당신은 반도체 및 빅테크 전문 애널리스트 AI입니다. 
기준일자인 {today_korean_str}을 바탕으로 주요 하이퍼스케일러(Amazon, Microsoft, Alphabet, Meta 등)의 실적 및 설비투자(CapEx) 기조, 특히 아마존 AWS의 분기별 매출액 증가율(감마값) 변화를 분석하여 한국 반도체(삼성전자, SK하이닉스 등) 주가에 미치는 선행 시그널과 대응 전략을 작성해 주세요.
(※ 주의: 마크다운 표 기호(|)는 절대 사용하지 마시고, 깔끔한 글머리 기호와 텍스트로만 작성해 주세요.)

1. AWS 실적 및 감마값 분석
- 최근 분기 AWS 매출액 및 전년/전분기 대비 증가율(YoY, QoQ) 변화
- 매출 성장 속도의 가속 또는 둔화 판정 (성장률의 변화율인 감마값 분석)
- 절대 매출 규모(모수)를 감안한 실질 클라우드 수요 평가

2. 빅테크 CapEx 투자 기조 요약
- 빅테크 4사(아마존, 마이크로소프트, 구글, 메타)의 데이터센터 및 AI 인프라 설비투자(CapEx) 가이던스 변화 추이

3. 한국 반도체(삼성전자·SK하이닉스) 영향 평가
- 클라우드 업체의 투자 피크아웃 또는 재개 시점이 메모리 반도체(HBM, DRAM, NAND) 수요, 재고, 가격에 미치는 영향 분석
- 현재 반도체 사이클 대비 위치 진단 (상승 초기 / 피크 근접 / 조정기 등)

4. 주가 대응 전략 및 체크포인트
- 투자자가 주목해야 할 차기 선행 지표 (예: 하이퍼스케일러 투자 발표 일정, 차분기 가이던스 등)
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
[빅테크 CapEx 및 AWS 매출 추적 긴급 브리핑]
기준일: {today_korean_str}

1. AWS 매출 및 감마값 분석
- 하이퍼스케일러 클라우드 부문의 성장 모멘텀이 유지되는지 여부와 매출 증가율의 둔화/가속(감마값) 추이를 모니터링해야 합니다.

2. 빅테크 CapEx 기조
- AI 인프라 투자가 지속되고 있으나, 투자 효율화 및 비용 통제 움직임이 동시에 나타나는지 점검이 필요합니다.

3. 한국 반도체 영향 평가
- 데이터센터 투자 흐름은 HBM 및 서버용 DRAM 수요의 직접적인 선행 지표이므로, 빅테크의 CapEx 가이던스 변화를 예의주시해야 합니다.

4. 대응 전략
- 실적 발표 시즌 전후로 하이퍼스케일러의 CapEx 상향/하향 조정 여부를 확인하고 포트폴리오 비중을 조절할 것을 권장합니다.
"""

    # -----------------------------------------------------------------------
    # 리포트 본문 구성 및 이메일 발송
    # -----------------------------------------------------------------------
    report_body = f"=========================================================\n"
    report_body += f" 📊 [{today_str}] 빅테크 CapEx 및 AWS 매출 추적 보고서\n"
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
    msg['Subject'] = f"[{today_str}] 빅테크CapEx및AWS매출분석"
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 성공적으로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    print("🚀 빅테크 CapEx 및 AWS 분석 스크립트 실행 시작...")
    run_bigtech_aws_analysis_pipeline()
