import sys
sys.stdout.reconfigure(encoding='utf-8')

from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import urllib3
import os
import time
import re
import xml.etree.ElementTree as ET
import csv
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# [환경 설정] - 평소에는 최근 며칠치만 가볍게 수집
#   COLLECT_DAYS : 며칠 전 기사까지 모을지 (기본 3일)
#   MAX_PAGES    : 소스별로 몇 페이지까지 볼지 (기본 10페이지, 기준일에 닿으면 그 전에 멈춤)
#   과거 기사를 보충하려면 Actions 의 Run workflow 에서 두 값을 크게 넣어 실행
# ==============================================================================
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")  # 👈 구글 시트 웹앱 URL
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")                    # 👈 ScraperAPI 키
SHEET_URL = os.environ.get("SHEET_URL")                                # 👈 시트 주소 (이미 있는 기사 주소를 한 번에 읽는 용도, 선택)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

now = datetime.now(timezone(timedelta(hours=9)))
today_str = now.strftime('%Y-%m-%d')

COLLECT_DAYS = int(os.environ.get("COLLECT_DAYS") or 3)
MAX_PAGES = int(os.environ.get("MAX_PAGES") or 10)
cutoff_date_str = (now - timedelta(days=COLLECT_DAYS)).strftime('%Y-%m-%d')

print(f"✅ 수집 기준일: {today_str}")
print(f"✅ 수집 대상 기간: {cutoff_date_str} ~ {today_str} (최근 {COLLECT_DAYS}일, 소스별 최대 {MAX_PAGES}페이지)")
if not SCRAPER_API_KEY:
    print("⚠️ SCRAPER_API_KEY 가 없습니다. 데일리메디·청년의사는 해외(GitHub) 서버에서 바로 접속하면 막혀 수집되지 않습니다.")
print("=" * 65)


# ==============================================================================
# [이미 시트에 있는 기사 주소] - 시작할 때 시트를 CSV로 한 번 읽어 둠
#   기사마다 웹앱에 보내 중복을 확인하면 1건에 3~4초씩 걸려 실행 시간(비공개 저장소 무료 한도)을 많이 씀
#   → 이미 있는 주소는 보내지 않고 건너뜀. 시트를 못 읽으면 예전처럼 모두 보내고 웹앱이 중복을 거름
# ==============================================================================
def load_known_links():
    m = re.search(r'/spreadsheets/d/([\w-]+)', SHEET_URL or '')
    if not m:
        print("ℹ️ SHEET_URL 이 없어 기사마다 웹앱으로 중복을 확인합니다.")
        return set()
    gid = re.search(r'[#&?]gid=(\d+)', SHEET_URL)
    url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    try:
        res = requests.get(url, timeout=60)
        rows = list(csv.reader(io.StringIO(res.content.decode('utf-8-sig'))))
        col = next(i for i, h in enumerate(rows[0]) if re.search(r'url|링크|주소', h, re.I) and not re.search(r'사진|이미지', h))
        links = {r[col].strip() for r in rows[1:] if len(r) > col and r[col].strip()}
        print(f"✅ 시트에 이미 있는 기사 주소 {len(links)}건을 읽었습니다.")
        return links
    except Exception as e:
        print(f"⚠️ 시트를 읽지 못해 기사마다 웹앱으로 중복을 확인합니다: {str(e)[:120]}")
        return set()


KNOWN = load_known_links()
known_skip = 0


# ==============================================================================
# [구글 시트 전송 함수]
# ==============================================================================
def send_to_google_sheet(title, link, pub_date, source):
    global known_skip
    if link in KNOWN:
        known_skip += 1
        return "duplicate"
    if not GOOGLE_SHEET_WEBHOOK_URL:
        print("   🚨 [설정 오류] GOOGLE_SHEET_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        return "no_webhook"

    formatted_date = pub_date.replace('.', '-')

    payload = {
        "collect_date": today_str,
        "source": source,
        "title": title,
        "pub_date": formatted_date,
        "link": link,
        "status": "",          # Gemini가 분석할 수 있도록 공란으로 전송
        "category": "",
        "summary_reason": "",
        "hospital": "",
        "region": "",
        "progress": "자료수집",
        "photo_url": ""
    }

    try:
        res = requests.post(GOOGLE_SHEET_WEBHOOK_URL, json=payload, timeout=30)
        res_json = res.json()
        if res_json.get("status") == "success":
            print(f"   ㄴ [저장 완료] ({formatted_date}) {title[:40]}...")
            KNOWN.add(link)
            return "success"
        elif res_json.get("status") == "duplicate":
            print(f"   ㄴ [중복 스킵] 이미 시트에 존재하는 기사입니다.")
            return "duplicate"
        else:
            print(f"   🚨 [구글 시트 응답 오류]: {res.text}")
    except Exception as e:
        print(f"   🚨 [구글 시트 전송 실패]: {e}")
    return "error"


def get_bypass_url(target_url, render=False, country=None):
    if not SCRAPER_API_KEY:
        return target_url
    bypass_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={target_url}"
    if render:
        bypass_url += "&render=true"
    if country:
        bypass_url += f"&country_code={country}"
    return bypass_url


def fetch(url, tries=3):
    for i in range(tries):
        try:
            res = requests.get(url, timeout=90, verify=False)
            if res.status_code == 200:
                return res
            print(f"   ⚠️ HTTP {res.status_code} ({i + 1}/{tries})")
        except Exception as e:
            print(f"   ⚠️ 접속 실패 ({i + 1}/{tries}): {str(e)[:120]}")
        time.sleep(5 * (i + 1) ** 2)
    raise RuntimeError("여러 번 시도했지만 페이지를 받지 못했습니다")


def mohw_full_title(link):
    # 복지부 목록은 긴 제목을 ".."로 자르므로 글 본문 페이지의 제목(board_view h2.title)을 씀 (하루 몇 건)
    try:
        res = fetch(link, tries=2)  # 복지부는 해외에서도 바로 열려 ScraperAPI 한도를 쓰지 않음
        h2 = BeautifulSoup(res.text, 'html.parser').select_one('.board_view h2.title')
        return h2.get_text(" ", strip=True) if h2 else ""
    except Exception as e:
        print(f"   ⚠️ 전체 제목 가져오기 실패: {str(e)[:80]}")
        return ""


# ==============================================================================
# [1] 보건복지부 [보도자료] (bid=0027)
# ==============================================================================
def collect_mohw_press():
    print("\n🔍 [1/5 보건복지부 보도자료] 수집 시작...")
    count = 0
    page = 1
    max_pages = MAX_PAGES

    while page <= max_pages:
        target_url = f"https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027&nPage={page}"
        url = get_bypass_url(target_url, country="kr")
        print(f"   -> {page}페이지 탐색 중...")

        try:
            res = fetch(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.tstyle_list tbody tr')
            if not rows:
                print("   더 이상 게시물이 없습니다.")
                break

            reached_cutoff = False
            for row in rows:
                tds = row.select('td')
                if len(tds) < 4: continue
                # 보도자료 테이블 등록일 (tds[3])
                date_text = tds[3].get_text(strip=True)

                if len(date_text) == 10 and date_text.startswith("20"):
                    if date_text < cutoff_date_str:
                        reached_cutoff = True
                        break

                    a_tag = row.select_one('td a')
                    if not a_tag or 'href' not in a_tag.attrs: continue
                    title = a_tag.get_text(strip=True).replace('새글', '').strip()
                    href = a_tag['href']
                    link = href if href.startswith("http") else "https://www.mohw.go.kr" + href
                    link = re.sub(r'nPage=\d+', 'nPage=1', link)
                    if title.endswith('..') and link not in KNOWN:
                        title = mohw_full_title(link) or title
                    if send_to_google_sheet(title, link, date_text, "보건복지부(보도자료)") == "success":
                        count += 1

            if reached_cutoff:
                print(f"   🏁 기준일({cutoff_date_str}) 도달 완료.")
                break

        except Exception as e:
            print(f"   🚨 보건복지부 보도자료 {page}페이지 에러: {e}")
            break

        page += 1
        time.sleep(1.5)

    print(f"   👉 보건복지부(보도자료) 신규 저장: {count}건")
    return count


# ==============================================================================
# [2] 보건복지부 [공지사항] (bid=0003)
# ==============================================================================
def collect_mohw_notice():
    print("\n🔍 [2/5 보건복지부 공지사항] 수집 시작...")
    count = 0
    page = 1
    max_pages = MAX_PAGES

    while page <= max_pages:
        target_url = f"https://www.mohw.go.kr/board.es?mid=a10501010100&bid=0003&nPage={page}"
        url = get_bypass_url(target_url, country="kr")
        print(f"   -> {page}페이지 탐색 중...")

        try:
            res = fetch(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.tstyle_list tbody tr')
            if not rows:
                print("   더 이상 게시물이 없습니다.")
                break

            reached_cutoff = False
            for row in rows:
                tds = row.select('td')
                if len(tds) < 4: continue
                date_text = tds[3].get_text(strip=True)

                if len(date_text) == 10 and date_text.startswith("20"):
                    if date_text < cutoff_date_str:
                        reached_cutoff = True
                        break

                    a_tag = row.select_one('td a')
                    if not a_tag or 'href' not in a_tag.attrs: continue
                    title = a_tag.get_text(strip=True).replace('새글', '').strip()
                    href = a_tag['href']
                    link = href if href.startswith("http") else "https://www.mohw.go.kr" + href
                    link = re.sub(r'nPage=\d+', 'nPage=1', link)
                    if title.endswith('..'):
                        title = mohw_full_title(link) or title
                    if send_to_google_sheet(title, link, date_text, "보건복지부(공지)") == "success":
                        count += 1

            if reached_cutoff:
                print(f"   🏁 기준일({cutoff_date_str}) 도달 완료.")
                break

        except Exception as e:
            print(f"   🚨 보건복지부 공지사항 {page}페이지 에러: {e}")
            break

        page += 1
        time.sleep(1.5)

    print(f"   👉 보건복지부(공지) 신규 저장: {count}건")
    return count


# ==============================================================================
# [3] 메디컬타임즈
# ==============================================================================
def collect_medicaltimes():
    print("\n🔍 [3/5 메디컬타임즈] 수집 시작...")
    count = 0
    page = 1
    max_pages = MAX_PAGES

    while page <= max_pages:
        target_url = f"https://www.medicaltimes.com/Main/News/List.html?page={page}"
        url = get_bypass_url(target_url)
        print(f"   -> {page}페이지 탐색 중...")

        try:
            res = fetch(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('article.newsList_cont')
            if not items:
                print("   더 이상 게시물이 없습니다.")
                break

            reached_cutoff = False
            for item in items:
                date_tag = item.select_one('.newsList_cont_date')
                if not date_tag: continue
                date_text = date_tag.get_text(strip=True).split(' ')[0]

                if len(date_text) == 10 and date_text.startswith("20"):
                    if date_text < cutoff_date_str:
                        reached_cutoff = True
                        break

                    headline_tag = item.select_one('.headLine')
                    if not headline_tag: continue
                    title = headline_tag.get_text(strip=True)
                    link = "https://www.medicaltimes.com" + item.select_one('a')['href']
                    if send_to_google_sheet(title, link, date_text, "메디컬타임즈") == "success":
                        count += 1

            if reached_cutoff:
                print(f"   🏁 기준일({cutoff_date_str}) 도달 완료.")
                break

        except Exception as e:
            print(f"   🚨 메디컬타임즈 {page}페이지 에러: {e}")
            break

        page += 1
        time.sleep(1.5)

    print(f"   👉 메디컬타임즈 신규 저장: {count}건")
    return count


# ==============================================================================
# [4] 데일리메디
# ==============================================================================
def collect_dailymedi():
    print("\n🔍 [4/5 데일리메디] 수집 시작...")
    count = 0
    page = 1
    max_pages = MAX_PAGES

    while page <= max_pages:
        target_url = f"https://www.dailymedi.com/news/news_list.php?ca_id=22&page={page}"
        url = get_bypass_url(target_url)
        print(f"   -> {page}페이지 탐색 중...")

        try:
            res = fetch(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.listNews li')
            if not items:
                print("   더 이상 게시물이 없습니다.")
                break

            reached_cutoff = False
            for item in items:
                date_tag = item.select_one('.news_list_date')
                if not date_tag: continue
                date_text = date_tag.get_text(strip=True).split(' ')[0]

                if len(date_text) == 10 and date_text.startswith("20"):
                    if date_text < cutoff_date_str:
                        reached_cutoff = True
                        break

                    stitle_tag = item.select_one('.stitle')
                    if not stitle_tag: continue
                    title = stitle_tag.get_text(strip=True)
                    a_tag = item.select_one('a')
                    if not a_tag or 'href' not in a_tag.attrs: continue
                    link = "https://www.dailymedi.com/news/" + a_tag['href'].replace('./', '')
                    link = re.sub(r'&page=\d+', '', link)
                    if send_to_google_sheet(title, link, date_text, "데일리메디") == "success":
                        count += 1

            if reached_cutoff:
                print(f"   🏁 기준일({cutoff_date_str}) 도달 완료.")
                break

        except Exception as e:
            print(f"   🚨 데일리메디 {page}페이지 에러: {e}")
            break

        page += 1
        time.sleep(1.5)

    print(f"   👉 데일리메디 신규 저장: {count}건")
    return count


# ==============================================================================
# [5] 청년의사
# ==============================================================================
def collect_docdocdoc():
    # 목록 페이지는 자바스크립트로 그려져 해외 서버에서 비어 보이므로 RSS(최근 약 50건, 2~3일치)로 수집
    print("\n🔍 [5/5 청년의사] 수집 시작 (RSS)...")
    count = 0
    try:
        res = fetch("https://www.docdocdoc.co.kr/rss/allArticle.xml")
        items = ET.fromstring(res.content).iter('item')
        for item in items:
            date_text = (item.findtext('pubDate') or '').strip()[:10]
            if not (len(date_text) == 10 and date_text.startswith("20")) or date_text < cutoff_date_str:
                continue
            title = (item.findtext('title') or '').strip()
            m = re.search(r'idxno=(\d+)', item.findtext('link') or '')
            if not title or not m: continue
            link = f"https://www.docdocdoc.co.kr/news/articleView.html?idxno={m.group(1)}"
            if send_to_google_sheet(title, link, date_text, "청년의사") == "success":
                count += 1
    except Exception as e:
        print(f"   🚨 청년의사 RSS 에러: {e}")

    print(f"   👉 청년의사 신규 저장: {count}건")
    return count


# ==============================================================================
# [메인 실행부]
# ==============================================================================
if __name__ == "__main__":
    print("🚀 보건복지부(보도자료/공지) + 3대 전문언론 기사 수집을 시작합니다...")
    start_time = time.time()

    total = (
        collect_mohw_press()   # 👈 새로 추가된 보건복지부 보도자료 게시판 (bid=0027)
        + collect_mohw_notice() # 보건복지부 공지사항 게시판 (bid=0003)
        + collect_medicaltimes()
        + collect_dailymedi()
        + collect_docdocdoc()
    )

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 65)
    print(f"🎉 수집 완료: 총 {total}개의 신규 기사가 구글 시트에 등록되었습니다! (소요 시간: {elapsed}초)")
    print(f"   (시트에 이미 있어 보내지 않은 기사: {known_skip}건)")
    print("=" * 65)
