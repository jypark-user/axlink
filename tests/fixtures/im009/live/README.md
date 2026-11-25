# IM-005A 실연동 시험자료 (GitHub)

IM-005A 4~5절의 GitHub 자료(TD-CON-1·TD-CON-3)를 실제 비공개 시험 저장소 두 곳에 만들어 두고,
AX Link 가 그 저장소를 원천으로 수집하는지 `tests/scenarios/test_live_github.py` 로 본다.
재생 서버(`replay*.py`) 결과로 대신하지 않는다. Redmine(TD-CON-2·4)은 여기 들어 있지 않다.

| 자료 | 저장소 | 내용(S0) |
|---|---|---|
| TD-CON-1 | `jypark-user/axlink-verify` | 이슈 G1~G5 #1~#5, PR TD-PR-1~3 #6~#8(모두 병합), 마일스톤 M-a #1(닫힘)·M-b #2, 라벨 「유형: 요구사항」, 커밋 TD-CMT-1·3·4, `docs/00-management/WBS.xlsx`(S0 실적), `docs/20-design/설계-민원조회.md`, 태그 `td-s0` |
| TD-CON-3 | `jypark-user/axlink-verify-web` | 이슈 W4 #4(#1~#3 은 만들었다 지움), 커밋 TD-CMT-W1, 태그 `td-s0` |

TD-ID → 실제 번호·SHA 는 `github-map.json` 에 있다. 시드가 원천에서 읽어 쓴다. 토큰·개인정보는 없다.

IM-005A 에 없는 커밋이 셋 있다. 파일을 넣는 초기 구성 커밋(`TD-SETUP-1`)과 PR #7·#8 의 head 커밋
(`TD-PR-2-HEAD`·`TD-PR-3-HEAD`)이다. head 커밋 메시지에는 요구사항 코드·`RM-` 참조를 넣지 않았다
(IM-005A 7.4 에 없는 추적 링크가 생기지 않게). PR #6 의 head 는 TD-CMT-3 이다.

## 환경변수

| 이름 | 쓰는 곳 | 비고 |
|---|---|---|
| `AXLINK_VERIFY_GH_TOKEN` | 시험(연결 등록·원천 비교) | **읽기 전용** fine-grained 토큰. 두 저장소에 Contents·Issues·Pull requests·Metadata 읽기. 시험은 이 변수에서만 토큰을 읽는다 |
| `AXLINK_LIVE=1` | 시험 | 없으면 `live` 시험은 건너뛴다 |
| `AXLINK_DATABASE_URL` | 시험 | 이름이 `_test` 로 끝나는 전용 DB |
| `AXLINK_TARGET_URL` | 원격 실행 | 예 `http://127.0.0.1:5174/ax-link`. 없으면 프로세스 안에서 돈다 |
| `AXLINK_VERIFY_GH_REPO` · `AXLINK_VERIFY_GH_REPO_WEB` | 시드·시험 | 저장소를 바꿀 때만. 대응표의 저장소와 다르면 시험은 건너뛴다 |

시드·S1 전환·복원(쓰기)은 이 PC 의 `gh` CLI 로그인으로 한다. 토큰을 파일에 적지 않는다.
push 는 `git -c credential.helper= -c "credential.helper=!gh auth git-credential"` 로 한다.

## 명령

```bash
# S0 시드(멱등. 있는 것은 건너뛰고 대응표를 다시 쓴다)
python -m tests.fixtures.im009.live_github seed
# 지금 상태(S0 / S1 / mixed)
python -m tests.fixtures.im009.live_github status
# S1 전환: TD-CMT-2(SW설계서_v0.9.docx 추가)와 WBS 3.2 85% 커밋을 push
python -m tests.fixtures.im009.live_github s1
# S0 로 되돌림: 파일 내용을 td-s0 와 같게 만드는 커밋을 push(force push 안 함)
python -m tests.fixtures.im009.live_github restore
```

`UC-011-S03` 시험이 S1 전환과 복원을 스스로 한다. 시험이 중간에 멈춰 저장소가 S1 으로 남으면 다음
실행이 시작할 때 복원한다(gh 로그인 필요). 복원은 이력을 지우지 않으므로 S1 을 돌릴 때마다 커밋이
셋(S1 둘, 복원 하나) 늘어난다. 시험은 고정 건수가 아니라 원천 API 건수와 비교하므로 영향이 없다.

## 실행

프로세스 안(전용 시험 DB):

```bash
docker exec axlink-test-postgres-1 createdb -U axlink live_axlink_test
MSYS_NO_PATHCONV=1 docker run --rm --network axlink-test_default \
  -v <워크트리>/db/migration:/flyway/sql:ro flyway/flyway:10 \
  -url=jdbc:postgresql://postgres:5432/live_axlink_test -user=axlink -password=axlink \
  -locations=filesystem:/flyway/sql migrate
AXLINK_DATABASE_URL=postgresql://axlink:axlink@127.0.0.1:15433/live_axlink_test AXLINK_LIVE=1 \
  pytest tests/scenarios/test_live_github.py -m live_tool --junitxml=var/verify/live-github.xml
```

원격(5174):

- 대상 서버는 GitHub(`api.github.com`)에 닿아야 하고, 커밋·PR 변경 파일을 받도록
  `AXLINK_COLLECT_CHANGE_FILES=true` 로 떠 있어야 한다(UC-011-S11 의 TD-CMT-1 변경 파일).
- 시험 프로세스의 `AXLINK_DATABASE_URL` 은 대상 서버와 같은 전용 시험 DB 를 가리킨다(다른 시나리오와 같은 조건).
  시험은 사업·계정을 만들고 끝에 지운다.

```bash
AXLINK_TARGET_URL=http://127.0.0.1:5174/ax-link AXLINK_DATABASE_URL=<5174 전용 시험 DB> AXLINK_LIVE=1 \
  pytest tests/scenarios/test_live_github.py -m live_tool --junitxml=var/verify/live-github-5174.xml
python scripts/verification_records.py record-junit var/verify/live-github-5174.xml \
  --mode live --tools github-live --env <5174 환경 이름> --proves api ...
```

각 시험은 junit 속성 `proves=live-tool` 을 남긴다. `--tools` 에 `replay` 가 들어가면 기록 스크립트가
live-tool 을 지우므로 넣지 않는다.

## 재생 시험과 다르게 보는 것

- 이슈·PR·마일스톤의 생성·닫힌 시각은 GitHub 이 정한다(시드한 날). IM-005A 의 날짜(예 TD-MS-5 닫힌 날
  2026-06-03) 대신 원천 API 값과 원시본·표준 모델 값이 같은지 본다. 마일스톤 기한과 커밋 저자 시각은
  IM-005A 값으로 넣었으므로 그 값과도 비교한다.
- 건수는 원천 API 건수와 비교한다(받침 커밋·S1 이력 때문에 IM-005A 7.3 의 고정 건수와 다르다).
- 원천 무기록(UC-010-S06·UC-050-S05·UC-051-S05)은 수집·확인 요청·조치 보고 전후의 원천 스냅숏
  (이슈·PR·커밋·마일스톤·라벨·브랜치·파일 목록, 갱신 시각)을 비교한다. 프로세스 안 실행은 어댑터가
  GitHub 에 보낸 요청이 모두 GET 인지도 본다.
- S1 커밋은 커미터 시각을 지금으로 둔다. 증분 수집의 `since` 필터가 커미터 시각을 보기 때문이다.
