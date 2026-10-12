/**
 * Google Apps Script for Medical News Scraping Automation
 * 구글 시트 > 확장 프로그램 > Apps Script에 붙여넣고 [배포] > [새 배포] > [웹 앱]으로 배포하세요.
 */

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("뉴스 스크랩") || ss.getSheets()[0];
    var data = JSON.parse(e.postData.contents);

    var lastRow = sheet.getLastRow();
    
    // 10번째 열(기사 URL, Col J) 기준 중복 검사
    if (lastRow > 1) {
      var urls = sheet.getRange(2, 10, lastRow - 1, 1).getValues().flat();
      if (urls.indexOf(data.link) !== -1) {
        return ContentService.createTextOutput(JSON.stringify({ status: "duplicate", message: "이미 등록된 기사입니다." }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }

    // 12개 컬럼 행 추가
    // 1.수집일자, 2.출처/매체, 3.기사 제목, 4.선별상태, 5.분류, 6.주요 내용 요약 및 AI 판정사유, 7.병원/기관명, 8.지역, 9.보도일자, 10.기사 URL, 11.진행상황, 12.대표사진 URL
    sheet.appendRow([
      data.collect_date || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd"),
      data.source || "",
      data.title || "",
      data.status || "",          // 수집 시 공란 -> Gemini가 매일 아침 분석하여 기입
      data.category || "",        // 수집 시 공란 -> Gemini가 매일 아침 분석하여 기입
      data.summary_reason || "",  // 수집 시 공란 -> Gemini가 매일 아침 분석하여 기입
      data.hospital || "",        // 수집 시 공란 -> Gemini가 매일 아침 분석하여 기입
      data.region || "",          // 수집 시 공란 -> Gemini가 매일 아침 분석하여 기입
      data.pub_date || "",
      data.link || "",
      data.progress || "자료수집",
      data.photo_url || ""
    ]);

    return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "구글 시트 행 추가 완료" }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "Medical News Webhook is active" }))
    .setMimeType(ContentService.MimeType.JSON);
}
