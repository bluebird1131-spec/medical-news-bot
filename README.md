# 🏥 병원 뉴스 자동화 파이프라인 (GitHub 수집 + Gemini AI 분석)

이 프로젝트는 **비용 0원($0)**으로 구축된 병원 신규 의료서비스 및 기술도입 뉴스 모니터링 시스템입니다.

---

## 🔄 2단계 자동화 작동 구조

```text
[1단계: GitHub Actions]  매일 06:00 KST
   └ 4개 매체 크롤링 → 기사 기본정보(출처, 제목, 일자, URL)를 구글 시트에 행 추가

[2단계: Gemini 자동화]   매일 09:00 KST
   └ 구글 시트의 신규 행 감지 → 선별상태, 분류, 판정사유/요약, 병원명, 지역 AI 분석 후 시트 업데이트
   └ Gemini 채팅창으로 "오늘의 핵심 선별 뉴스 브리핑" 보고 전달
```

---

## 📁 파일 구성
- `news.py`: 4개 매체 가벼운 수집 및 구글 시트 전송 스크립트 (외부 AI API 불필요)
- `google_apps_script.js`: 구글 시트 Apps Script에 붙여넣을 Webhook 코드
- `.github/workflows/scrape.yml`: 매일 새벽 6시 GitHub Actions 자동 실행 워크플로우
- `requirements.txt`: 필수 파이썬 라이브러리 목록

---

## 🚀 설정 방법

### 1. 구글 시트 웹앱(Webhook) 배포
1. 구글 시트 `신규 의료서비스 및 기술도입 뉴스 스크랩 (자동화)` 열기
2. 상단 메뉴 **확장 프로그램** → **Apps Script** 클릭
3. `google_apps_script.js` 내용 붙여넣고 저장(Ctrl+S)
4. 우측 상단 **[배포]** → **[새 배포]**
   - 유형: **웹 앱**
   - 설명: `News Webhook`
   - 다음 사용자 권한으로 실행: **나(내 계정)**
   - 액세스 권한이 있는 사용자: **모든 사용자(Anyone)** 👈 *필수*
5. 배포 완료 후 나타나는 **웹 앱 URL** 복사

### 2. GitHub Secrets 등록
GitHub 저장소의 **Settings** → **Secrets and variables** → **Actions**에 아래 Secret을 등록합니다:
- `GOOGLE_SHEET_WEBHOOK_URL`: 1단계에서 복사한 웹 앱 URL
- `SCRAPER_API_KEY`: (선택) ScraperAPI 키

### 3. 테스트 실행
- GitHub 저장소의 **Actions** 탭에서 **Daily Medical News Collector** 워크플로우를 선택하고 **Run workflow**를 누르면 즉시 수집 테스트가 가능합니다.
- 로컬 실행:
  ```bash
  pip install -r requirements.txt
  python news.py
  ```
