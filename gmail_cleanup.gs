/**
 * 지메일 한 번에 정리 (Google Apps Script)
 *
 * 사용법 (아이패드 Safari 가능)
 *  1. script.google.com → 새 프로젝트
 *  2. 기존 코드를 지우고 이 파일 내용 전체 붙여넣기 → 저장(💾)
 *  3. 위쪽 함수 선택에서 「정리시작」 고르고 ▶ 실행
 *  4. 권한 요청 → 본인 계정 선택 → "고급" → "(안전하지 않음)으로 이동" → 허용
 *     (본인이 만든 스크립트라서 뜨는 경고입니다)
 *  5. 끝. 10분마다 자동으로 이어서 처리하고, 다 끝나면 스스로 멈춥니다.
 *     진행 상황은 왼쪽 「실행」 메뉴 로그에서 볼 수 있습니다.
 *
 * - 삭제는 하지 않습니다. 라벨을 붙이고 '보관처리'만 합니다(검색하면 다 나옴).
 * - 별표 메일은 건드리지 않습니다.
 */

// [검색어, 붙일 라벨(없으면 null), 보관처리 여부]
// 위에서부터 순서대로 처리합니다.
var RULES = [
  ['in:inbox from:googlealerts-noreply@google.com', '업계뉴스', true],
  ['in:inbox -is:starred from:(linkedin.com OR glassdoor.com OR rocketpunch.com)', '채용알림', true],
  ['in:inbox -is:starred from:(businesstimes.com.sg OR medium.com OR wishket.com OR ted.com OR learn.mit.edu OR reclaim.ai OR lumosity.com OR investingmail.com OR coursera.org)', '읽을거리', true],
  ['in:inbox -is:starred from:(taskade.com OR superlist.com OR craft.do OR monday.com OR asana.com OR akiflow.com OR clickup.com OR evernote.com OR gamma.app OR email.claude.com OR mail.cursor.com OR email.openai.com)', '읽을거리', true],
  ['in:inbox -is:starred from:(lilys.ai OR monica.im OR napkin.ai OR wrtn.io OR linermail.com OR offlight.work OR heybunny.io OR updates.notion.so OR updates.notion.com OR smartthings.com OR wconcept.co.kr OR dropbox.com)', '읽을거리', true],
  ['in:inbox -is:starred from:(no-reply@todoist.com OR noreply-accounts@google.com)', null, true],
  ['in:inbox from:(uber.com OR 29cm.co.kr)', 'Receipts', true],
  ['in:inbox newer_than:6m from:(no-reply@agoda.com OR agoda-messaging.com) -label:여행', '여행', false],
  ['in:inbox newer_than:1y from:(recmail.lg.com OR saramin.co.kr OR jobkorea.co.kr OR wanted.co.kr OR greetinghr.com OR ninehire.com OR remember.co.kr) -label:커리어', '커리어', false],
  ['in:inbox newer_than:1y from:(wooricard.com OR stripe.com OR googleplay-noreply@google.com OR payments-noreply@google.com) -label:결제·구독', '결제·구독', false],
  ['in:inbox category:promotions -is:starred', null, true],
  // 3개월 지난 메일은 라벨이 있어도 받은편지함에서 뺌 (라벨은 그대로 남음)
  ['in:inbox -is:starred older_than:3m', null, true],
  // 마지막: 위에서 남긴 것(별표·여행·결제·커리어) 빼고 전부 보관
  ['in:inbox -is:starred -label:여행 -label:결제·구독 -label:커리어', null, true]
];

var BATCH = 100;            // Gmail이 한 번에 처리할 수 있는 최대 개수
var TIME_LIMIT_MS = 5 * 60 * 1000; // 실행 1회 6분 제한 전에 멈춤
var TRIGGER_FN = '정리실행';

function 정리시작() {
  정리중지();
  ScriptApp.newTrigger(TRIGGER_FN).timeBased().everyMinutes(10).create();
  Logger.log('10분마다 자동 실행을 걸었습니다. 지금 1회 바로 실행합니다.');
  정리실행();
}

function 정리중지() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === TRIGGER_FN) ScriptApp.deleteTrigger(t);
  });
}

function 정리실행() {
  var start = Date.now();
  var labels = {};
  var total = 0;

  for (var i = 0; i < RULES.length; i++) {
    var q = RULES[i][0], name = RULES[i][1], archive = RULES[i][2];
    if (name && !labels[name]) {
      labels[name] = GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
    }
    while (true) {
      if (Date.now() - start > TIME_LIMIT_MS) {
        Logger.log('시간 제한으로 멈춤. 이번 실행 처리: ' + total + '개. 10분 뒤 자동으로 이어갑니다.');
        return;
      }
      var threads = GmailApp.search(q, 0, BATCH);
      if (threads.length === 0) break;
      if (name) labels[name].addToThreads(threads);
      if (archive) GmailApp.moveThreadsToArchive(threads);
      total += threads.length;
      Logger.log((name || '보관') + ': ' + threads.length + '개 처리 (누적 ' + total + ')');
      if (!archive && threads.length < BATCH) break; // 라벨만 붙이는 규칙은 한 바퀴면 충분
    }
  }
  정리중지();
  Logger.log('✅ 전부 끝났습니다. 이번 실행 처리: ' + total + '개. 자동 실행을 껐습니다.');
}
