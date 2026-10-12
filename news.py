import sys
sys.stdout.reconfigure(encoding='utf-8')

from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# [환경 설정] - 가벼운 수집 전용 봇 (외부 AI API 불필요)
# ==============================================================================
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")  # 👈 구글 시트 웹앱 URL
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")                    # 👈 ScraperAPI 키

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

now = datetime.now(timezone(timedelta(hours=9)))
today_str = now.strftime('%Y-%m-%d')
target_dates_hyphen = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(0, 5)]
target_dates_dot = [(now - timedelta(days=i)).strftime('%Y.%m.%d') for i in range(0, 5)]

print(f"✅ 수집 기준일: {today_str}")
print(f"✅ 수집 대상 날짜 범위 (최근 5일): {target_dates_hyphen}")


# ==============================================================================
# [구글 시트 전송 함수] - 기본 정보만 추가, AI 판단 필드는 비워둠 (Gemini가 매일 분석)
# ==============================================================================
def send_to_google_sheet(title, link, pub_date, source):
    if not GOOGLE_SHEET_WEBHOOK_URL:
        print("   🚨 [설정 오류] GOOGLE_SHEET_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        return "no_webhook"

    payload = {
        "collect_date": today_str,
        "source": source,
        "title": title,
        "pub_date": pub_date.replace('.', '-'),
        "link": link,
        "status": "",          # Gemini가 채움
        "category": "",        # Gemini가 채움
        "summary_reason": "",  # Gemini가 채움
        "hospital": "",        # Gemini가 채움
        "region": "",          # Gemini가 채움
        "progress": "자료수집",
        "photo_url": ""
    }

    try:
        res = requests.post(GOOGLE_SHEET_WEBHOOK_URL, json=payload, timeout=30)
        res_json = res.json()
        if res_json.get("status") == "success":
            print(f"   ㄴ [구글 시트 저장 완료] {title}")
            return "success"
        elif res_json.get("status") == "duplicate":
            print(f"   ㄴ [중복 스킵] 이미 구글 시트에 존재하는 기사입니다.")
            return "duplicate"
        else:
            print(f"   🚨 [구글 시트 오류]: {res.text}")
    except Exception as e:
        print(f"   🚨 [구글 시트 전송 실패]: {e}")
    return "error"


# ==============================================================================
# [사이트별 수집 함수들]
# ==============================================================================
def get_bypass_url(target_url, render=False, country=None):
    if not SCRAPER_API_KEY:
        return target_url
    bypass_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={target_url}"
    if render:
        bypass_url += "&render=true"
    if country:
        bypass_url += f"&country_code={country}"
    return bypass_url

def collect_mohw():
    print("\n🔍 [보건복지부] 수집 시작...")
    target_url = "https://www.mohw.go.kr/board.es?mid=a10501010100&bid=0003"
    url = get_bypass_url(target_url, country="kr")
    count = 0
    try:
        res = requests.get(url, verify=False, timeout=90)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.tstyle_list tbody tr')
        if not rows:
            print("   🚨 복지부 게시물을 찾지 못했습니다.")
            return 0
        print(f"   -> 사이트 게시물 {len(rows)}개 확인됨")
        for row in rows:
            tds = row.select('td')
            if len(tds) < 4: continue
            date_text = tds[3].get_text(strip=True)
            if date_text in target_dates_hyphen:
                title = tds[2].get_text(strip=True).replace('새글', '').strip()
                link = "https://www.mohw.go.kr" + tds[2].select_one('a')['href']
                print(f"   -> [수집 대상] {title} ({date_text})")
                if send_to_google_sheet(title, link, date_text, "보건복지부") == "success":
                    count += 1
    except Exception as e:
        print(f"   🚨 복지부 에러: {e}")
    return count

def collect_medicaltimes():
    print("\n🔍 [메디컬타임즈] 수집 시작...")
    target_url = "https://www.medicaltimes.com/Main/News/List.html"
    url = get_bypass_url(target_url)
    count = 0
    try:
        res = requests.get(url, verify=False, timeout=90)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('article.newsList_cont')
        print(f"   -> 사이트 게시물 {len(items)}개 확인됨")
        for item in items:
            date_tag = item.select_one('.newsList_cont_date')
            if not date_tag: continue
            date_text = date_tag.get_text(strip=True).split(' ')[0]
            if date_text in target_dates_hyphen:
                title = item.select_one('.headLine').get_text(strip=True)
                link = "https://www.medicaltimes.com" + item.select_one('a')['href']
                print(f"   -> [수집 대상] {title} ({date_text})")
                if send_to_google_sheet(title, link, date_text, "메디컬타임즈") == "success":
                    count += 1
    except Exception as e:
        print(f"   🚨 메디컬타임즈 에러: {e}")
    return count

def collect_dailymedi():
    print("\n🔍 [데일리메디] 수집 시작...")
    target_url = "https://www.dailymedi.com/news/news_list.php?ca_id=22"
    url = get_bypass_url(target_url)
    count = 0
    try:
        res = requests.get(url, verify=False, timeout=90)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('.listNews li')
        print(f"   -> 사이트 게시물 {len(items)}개 확인됨")
        for item in items:
            date_tag = item.select_one('.news_list_date')
            if not date_tag: continue
            date_text = date_tag.get_text(strip=True).split(' ')[0]
            if date_text in target_dates_hyphen:
                title = item.select_one('.stitle').get_text(strip=True)
                link = "https://www.dailymedi.com/news/" + item.select_one('a')['href'].replace('./', '')
                print(f"   -> [수집 대상] {title} ({date_text})")
                if send_to_google_sheet(title, link, date_text, "데일리메디") == "success":
                    count += 1
    except Exception as e:
        print(f"   🚨 데일리메디 에러: {e}")
    return count

def collect_docdocdoc():
    print("\n🔍 [청년의사] 수집 시작...")
    target_url = "https://www.docdocdoc.co.kr/news/articleList.html?view_type=sm"
    url = get_bypass_url(target_url, render=True)
    count = 0
    try:
        res = requests.get(url, verify=False, timeout=90)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('#section-list > ul.type2 > li')
        print(f"   -> 사이트 게시물 {len(items)}개 확인됨")
        for item in items:
            date_text = item.select('span.byline em')[-1].get_text(strip=True).split(' ')[0]
            if date_text in target_dates_dot:
                title = item.select_one('h4.titles a').get_text(strip=True)
                link = "https://www.docdocdoc.co.kr" + item.select_one('h4.titles a')['href']
                print(f"   -> [수집 대상] {title} ({date_text})")
                if send_to_google_sheet(title, link, date_text, "청년의사") == "success":
                    count += 1
    except Exception as e:
        print(f"   🚨 청년의사 에러: {e}")
    return count

if __name__ == "__main__":
    print("=" * 60)
    print("🏥 병원 뉴스 수집 봇 (구글 시트 연동 모드)")
    print("=" * 60)
    total = collect_mohw() + collect_medicaltimes() + collect_dailymedi() + collect_docdocdoc()
    print(f"\n🚀 최종 결과: 총 {total}개의 신규 기사가 구글 시트에 등록되었습니다.")
