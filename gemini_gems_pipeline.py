import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. 환경 및 사용자 설정 (본인 정보로 입력)
# ---------------------------------------------------------------------------

# Gemini API 키 (Google AI Studio에서 발급받은 키 입력)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Gmail 계정 설정
SENDER_EMAIL = "junghye.chae@gmail.com"
SENDER_APP_PASSWORD = "cjohbodxkkaeciuk"  # 구글 계정에서 발급받은 16자리 앱 비밀번호 (공백 없이)
RECEIVER_EMAIL = "junghye.chae@gmail.com"

# Google Sheets 서비스 계정 키 파일 경로
CREDS_FILE = "service_account.json"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def get_gspread_client():
    """구글 시트 접근용 인증 클라이언트를 반환합니다."""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[경고] 구글 시트 서비스 계정 인증 실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 2. 보조 기능: 외부 시트 데이터 불러오기
# ---------------------------------------------------------------------------

def fetch_daily_macro_sheet_data(gc):
    """'매일 아침 자동 갱신용' 시트 데이터 읽기"""
    if not gc:
        return "(시트 접근 불가 - 인증 오류)"
    try:
        doc = gc.open("매일 아침 자동 갱신용")
        sheet = doc.get_worksheet(0)
        data = sheet.get("A1:C68")
        return "\n".join([" | ".join(row) for row in data])
    except Exception as e:
        return f"(시트 데이터 로드 실패: {e})"


def fetch_email_links_sheet_data(gc):
    """'이메일 알림 링크 수집' 시트 데이터 읽기"""
    if not gc:
        return "(시트 접근 불가 - 인증 오류)"
    try:
        doc = gc.open("이메일 알림 링크 수집")
        sheet = doc.get_worksheet(0)
        all_records = sheet.get_all_values()
        
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        filtered = [f"날짜: {r[0]} | 본문: {r[2]}" for r in all_records if len(r) >= 3 and (today in r[0] or yesterday in r[0])]
        return "\n\n".join(filtered) if filtered else "(최근 수집된 뉴스 데이터가 없습니다.)"
    except Exception as e:
        return f"(시트 데이터 로드 실패: {e})"


# ---------------------------------------------------------------------------
# 3. 메인 파이프라인
# ---------------------------------------------------------------------------

def run_gems_pipeline():
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_korean_str = datetime.now().strftime("%Y년 %m월 %d일")
    
    gc = get_gspread_client()
    
    # 1) 구글 시트 데이터 사전 수집
    print("구글 시트 외부 데이터 사전 조회 중...")
    macro_sheet_text = fetch_daily_macro_sheet_data(gc)
    email_news_text = fetch_email_links_sheet_data(gc)
    
    # 2) '구글젬스 자동화' 시트에서 Gems 목록 읽기
    gems_list = []
    if gc:
        try:
            config_doc = gc.open("구글젬스 자동화")
            config_sheet = config_doc.get_worksheet(0)
            rows = config_sheet.get_all_records()
            for r in rows:
                gems_list.append({
                    "name": str(r.get("젬스이름", "")).strip(),
                    "instruction": str(r.get("인스트럭션", "")).strip(),
                    "prompt": str(r.get("프롬프트", "")).strip()
                })
        except Exception as e:
            print(f"[오류] '구글젬스 자동화' 시트를 읽는데 실패했습니다: {e}")

    # 3) 보고서 헤더 생성
    report_body = f"=========================================================\n"
    report_body += f" 📊 [{today_str}] 데일리 금융 매크로 & 반도체 통합 보고서\n"
    report_body += f"=========================================================\n\n"

    # 4) 각 Gems 순차 실행
    for idx, gem in enumerate(gems_list, 1):
        gem_name = gem["name"]
        instruction = gem["instruction"]
        prompt = gem["prompt"]
        
        print(f"[{idx}/{len(gems_list)}] 실행 중: {gem_name}...")

        # 동적 프롬프트 교체
        if "@구글 스프레드시트 매일 아침 자동 갱신용" in prompt:
            prompt = f"다음은 시트에서 직접 추출한 데이터입니다:\n\n{macro_sheet_text}\n\n위 데이터를 바탕으로 분석을 진행해 줘."
        elif "@구글 스프레드시트 이메일 알림 링크 수집" in prompt:
            prompt = f"다음은 수집된 최신 뉴스 데이터입니다:\n\n{email_news_text}\n\n위 뉴스 내용을 바탕으로 주가 영향 리포트를 작성해 줘."
        elif "해당날짜를 넣어줘" in prompt:
            prompt = f"{today_korean_str} 기준 구리 시장 선물 차트, LME 재고, CFTC 투기적 포지션 분석 보고서를 작성해 줘."

        # 분당 요청 수가 과도하게  몰리지 않도록 3초 간격 휴식
        time.sleep(3)

        try:
            # Gemini API 호출
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.2,
                    tools=[{"google_search": {}}]
                )
            )
            
            result_text = response.text.strip() if response.text else "응답 내용 없음"
            
            report_body += f"■ {gem_name}\n"
            report_body += f"---------------------------------------------------------\n"
            report_body += f"{result_text}\n\n\n"

        except Exception as e:
            err_msg = str(e)
            # API 한도 초과 오류 발생 시 깔끔하게 정돈된 메시지 출력
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                clean_err = "[안내] Gemini API 일일 무료 호출 한도(Quota)가 초과되어 분석 데이터를 불러오지 못했습니다."
            else:
                clean_err = f"[실행 오류]: {err_msg[:120]}..."
                
            print(f"   └ {clean_err}")
            report_body += f"■ {gem_name}\n"
            report_body += f"---------------------------------------------------------\n"
            report_body += f"{clean_err}\n\n\n"

    # 5) 완성된 보고서 이메일 전송
    send_email(report_body, today_str)


# ---------------------------------------------------------------------------
# 4. 이메일 발송 함수
# ---------------------------------------------------------------------------

def send_email(content, today_str):
    print("이메일 발송 준비 중...")
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[{today_str}] 데일리 금융 매크로 & 반도체 통합 보고서"
    
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        # 587 (TLS) 보안 포트 적용
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 성공적으로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


# ---------------------------------------------------------------------------
# 5. 스크립트 실행 시작점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("🚀 스크립트 실행 시작...")
    run_gems_pipeline()
