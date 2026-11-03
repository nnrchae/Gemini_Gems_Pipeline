import os
import json
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. 환경 및 사용자 설정 (GitHub Secrets / 환경변수에서 불러옴)
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")

client = genai.Client(api_key=GEMINI_API_KEY)

CREDS_FILE = "service_account.json"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def get_gspread_client():
    """구글 시트 접근용 인증 클라이언트를 반환합니다."""
    try:
        if SERVICE_ACCOUNT_JSON and not os.path.exists(CREDS_FILE):
            try:
                json_data = json.loads(SERVICE_ACCOUNT_JSON)
                with open(CREDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                with open(CREDS_FILE, "w", encoding="utf-8") as f:
                    f.write(SERVICE_ACCOUNT_JSON)

        if not os.path.exists(CREDS_FILE):
            print("[경고] service_account.json 파일이 존재하지 않습니다.")
            return None

        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[경고] 구글 시트 서비스 계정 인증 실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 2. 추가 매크로 지표 자동 수집 및 71행 이후 업데이트 함수
# ---------------------------------------------------------------------------

def auto_update_macro_indicators(client, doc):
    """Gemini와 웹 검색을 활용해 추가 지표를 수집하고 시트 71행 이후에 자동으로 기록합니다."""
    print("추가 매크로 지표(PMI, 소비자심리, 기업이익, 주택지표, 순유동성) 자동 수집 중...")
    
    prompt_update = """
    당신은 거시경제 데이터 수집가입니다. Google 검색을 활용하여 다음 5가지 경제 지표의 가장 최신 수치(및 비교 기준값)를 정확히 찾아주세요.
    반드시 아래 지정된 JSON 형식으로만 응답해야 하며, 마크다운 코드블록이나 다른 텍스트를 포함하지 마세요.

    [수집 대상 지표]
    1. 주요국 제조업 PMI (미국 ISM 제조업 PMI 및 중국 최신값)
    2. 주요국 소비자 신뢰 지수 (미국 미시간대 또는 컨퍼런스보드 최신값)
    3. 기업 이익 성장률 (S&P 500 최근 분기 또는 YoY 이익증가율 전망치/실적)
    4. 주요국 주택 시장 지표 (미국 기존주택판매 또는 주택가격지수 최신값)
    5. 연준 순유동성 (현재 연준 총자산 - TGA - RRP 대략적 현재 추정치 및 6개월 전 기준값)

    [출력 JSON 포맷]
    {
      "indicators": [
        ["주요국 제조업 PMI", "미국 PMI / 중국 PMI 최신값", "최신 웹 검색 기준"],
        ["주요국 소비자 신뢰 지수", "지수값 최신", "최신 웹 검색 기준"],
        ["기업 이익 성장률 (YoY)", "S&P 500 이익증가율", "최신 웹 검색 기준"],
        ["주요국 주택 시장 지표", "지수/판매량 최신", "최신 웹 검색 기준"],
        ["연준 순유동성 (현재/6개월전)", "현재값 / 6개월전값", "최신 웹 검색 기준"]
      ]
    }
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_update,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text_resp = response.text.strip()
        
        # JSON 파싱 안정화 처리
        if "```json" in text_resp:
            text_resp = text_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in text_resp:
            text_resp = text_resp.split("```")[1].split("```")[0].strip()
            
        data_json = json.loads(text_resp)
        indicators = data_json.get("indicators", [])
        
        if indicators and doc:
            sheet = doc.get_worksheet(0)
            for i, row_data in enumerate(indicators, start=71):
                sheet.update(f"A{i}:C{i}", [row_data])
            print("✅ 구글 시트 71행 이후 추가 지표 자동 업데이트 성공!")
    except Exception as e:
        print(f"⚠️ 추가 지표 자동 업데이트 중 오류 발생 (기존 데이터 유지): {e}")


# ---------------------------------------------------------------------------
# 3. 구글 시트 데이터 불러오기 (범위 확장 A1:C80)
# ---------------------------------------------------------------------------

def fetch_daily_macro_sheet_data(gc, doc):
    """'매일 아침 자동 갱신용' 시트 A1:C80 데이터 읽기"""
    if not gc or not doc:
        return "(시트 접근 불가 - 인증 오류)"
    try:
        sheet = doc.get_worksheet(0)
        data = sheet.get("A1:C80")
        if not data:
            return "(시트에 데이터가 없습니다.)"
        return "\n".join([" | ".join(row) for row in data])
    except Exception as e:
        return f"(시트 데이터 로드 실패: {e})"


# ---------------------------------------------------------------------------
# 4. 메인 파이프라인 (통합 매크로 분석)
# ---------------------------------------------------------------------------

def run_macro_analysis_pipeline():
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_korean_str = datetime.now().strftime("%Y년 %m월 %d일")
    
    gc = get_gspread_client()
    doc = None
    if gc:
        try:
            doc = gc.open("매일 아침 자동 갱신용")
            # 1. 71행 이후 추가 지표 자동 수집 및 업데이트 선행 실행
            auto_update_macro_indicators(client, doc)
        except Exception as e:
            print(f"구글 시트 오픈 또는 자동 업데이트 실패: {e}")
    
    print("구글 시트 외부 데이터 사전 조회 중...")
    macro_sheet_text = fetch_daily_macro_sheet_data(gc, doc)

    # -----------------------------------------------------------------------
    # System Instruction & Prompt 정의 (추가 지표 적극 반영)
    # -----------------------------------------------------------------------
    system_instruction = """
너는 거시경제 지표 및 증시 수급 데이터를 바탕으로 현재 시장의 위치와 하락장 위험도를 객관적으로 진단하는 전문가야.
막연한 공포나 낙관론을 배제하고 제공된 수치 데이터(시트 기본 데이터 및 71행 이후 자동 수집된 PMI, 소비자심리, 기업이익, 주택지표, 순유동성 포함) 및 웹 검색을 통한 최신 지표 기반으로만 분석해 줘.

[주의 사항]
- 시트 데이터와 웹 검색을 통해 확보한 최신 수치를 모두 활용하여 정확하게 분석할 것.
- 이미지/색상이 아닌 데이터의 수치와 (+/-) 부호를 바탕으로 상승/하락을 판단할 것.
- 거시경제 애널리스트와 같은 신뢰감 있는 전문가 톤을 유지할 것.
"""

    prompt = f"""
기준일자: {today_korean_str}

아래는 '매일 아침 자동 갱신용' 구글 스프레드시트(A1:C80)에서 직접 추출한 최신 지표 데이터입니다:

========================================
[구글 시트 수집 데이터]
{macro_sheet_text}
========================================

위 데이터(VIX 지수, 공포&탐욕지수, 주요 미국 주식지수, 주요 종목 및 **71행 이후에 추가된 제조업 PMI, 소비자 신뢰 지수, 기업 이익 성장률, 주택 시장 지표, 연준 순유동성 데이터** 포함)와 **필요 시 최신 웹 검색 데이터**를 바탕으로 아래 **2가지 파트**로 작성해 줘.

---

### [PART 1. 거시경제 지표 그룹별 분석]
1. 각 지표를 5가지 그룹으로 나누어 수치와 함께 설명할 것. (추가된 경제 지표들도 적절한 그룹에 포함하여 심도 있게 다룰 것)
2. 수치 나열에 그치지 말고, 지표 간의 상관관계를 분석하여 현재 경제 상황을 한 문장으로 정의할 것.
3. 시장의 상방 요인과 하방 요인을 정리한 '총평'을 작성할 것.

---

### [PART 2. 매크로 리스크 진단기 (Macro Health Checker)]
아래 8대 핵심 지표 위험 판단 기준(Danger Trigger)에 근거하여 시트 데이터 및 웹 검색을 통해 확인 가능한 항목을 파악하고 위험도를 진단해 줘.

[8대 판단 기준]
1. 장단기 금리차 (10Y-2Y): Bull Steepening(금리 인하로 인한 역전 해소) 시 경고
2. 실질 근간 금리: [기준금리 - Core CPI] >= +1.5%p 시 경고
3. 삼의 법칙 (Sahm Rule): 최근 3개월 평균 실업률이 12개월 최저치 대비 +0.50%p 이상 상승 시 경고
4. MMF 대비 마진 데트 비율: [마진 데트 ÷ MMF 잔고] > 0.25 시 경고
5. 연준 순유동성: [연준 총자산 - TGA - RRP] 반기 연속 감소 시 경고 (시트 71행 이후에 수집된 순유동성 데이터 적극 활용)
6. 하이일드 스프레드: > 400bp (4.0%p) 돌파 시 경고
7. 빅테크 평균 PEG: > 2.0배 초과 시 경고 (웹 검색 기반 최신 추정치 활용)
8. 자사주 매입 규모: 전년 대비 -15% 이상 축소 시 경고

[위험도 4단계 종합 판정 기준]
- 0~1개 작동: [안정] 정상적인 투자 유지
- 2~3개 작동: [주의] 현금 비중 10~20% 확보 검토
- 4~5개 작동 (또는 Bull Steepening + 삼의 법칙 동시 작동): [경계] 현금/국채 비중 30~40% 확대
- 6개 이상 작동 (또는 하이일드 급등 + 순유동성 축소 동시 작동): [위험] 주식 비중 최소화 및 방어 자산 전환

[PART 2 출력 형식]
1. 종합 위험도 판정: [안정 / 주의 / 경계 / 위험] 및 위험 지표 개수 (X / 8개)
2. 트리거 작동 지표 리스트: 경고 기준을 넘어선 지표, 해당 수치, 그리고 그 이유
3. 핵심 위험 요인 요약: 현재 시장의 가장 취약한 고리 (2~3줄)
4. 추천 자산 배분 가이드: 현금, 방어주, 성장주 등의 비중 조율 제언
"""

    print("Gemini API 분석 요청 중 (웹 검색 툴 활성화)...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        analysis_result = response.text.strip() if response.text else "응답 내용 없음"
    except Exception as e:
        analysis_result = f"[실행 오류 발생]: {e}"
        print(analysis_result)

    # -----------------------------------------------------------------------
    # 리포트 본문 구성 및 이메일 발송
    # -----------------------------------------------------------------------
    report_body = f"=========================================================\n"
    report_body += f" 📊 [{today_str}] 매크로 통합 분석 보고서\n"
    report_body += f"=========================================================\n\n"
    report_body += analysis_result

    send_email(report_body, today_str)


# ---------------------------------------------------------------------------
# 5. 이메일 발송 함수
# ---------------------------------------------------------------------------

def send_email(content, today_str):
    print("이메일 발송 준비 중...")
    
    if not SENDER_EMAIL or not SENDER_APP_PASSWORD or not RECEIVER_EMAIL:
        print("❌ 이메일 발송 실패: SENDER_EMAIL, SENDER_APP_PASSWORD, RECEIVER_EMAIL 환경변수(Secrets)를 확인해 주세요.")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[{today_str}] 매크로분석"
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 성공적으로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    print("🚀 매크로분석 스크립트 실행 시작...")
    run_macro_analysis_pipeline()
