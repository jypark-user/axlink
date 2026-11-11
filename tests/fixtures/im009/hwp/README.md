# IM-009 시험자료 HWP·HWPX (가상 시험자료)

이 폴더의 파일 세 건은 AX Link 검증용으로 만든 **가상 시험자료**다. 실제 회의록이 아니다.
문서 첫 줄에 「가상 시험자료 · 실제 계약 문서가 아님」을 적었다. 한컴오피스 한글 2024 의 자동화
개체(`HWPFrame.HwpObject`)로 만들었다. 확장자만 바꾸거나 다른 형식을 감싼 파일이 아니다.

| 자료 | 파일 | 형식 | 내용(IM-009 4.4) | SHA-256 |
|---|---|---|---|---|
| TD-DOC-12 | 설계검토회의록.hwp | HWP 5.0 바이너리(판 5.1.1.0) | 표 1개 3행×4열(머리글 항목·검토자·결과·비고 + 자료 2행), 문단 3개, 2쪽 | `c2b2cace302710fdf912ac9dd0f743edb791064af031de7838814f3e76e9bcba` |
| TD-DOC-13 | 설계검토회의록.hwpx | HWPX(OWPML) | TD-DOC-12 와 같은 내용 | `d2f06f8a0dd717f3fc405b1bafa0f65991a46544a20390eb79f1a39ca49a38ef` |
| TD-DOC-15 | 암호문서.hwp | HWP 5.0, 문서 암호 | TD-DOC-12 와 같은 내용에 암호를 걸었다. 시험자료 암호 `axlink-test-1234`(비밀 아님) | `048db9092cb2c5161fa603f79fd446a53a2efa6e14d8e6036e07d0168ce8b48b` |

시험은 이 파일을 그대로 쓴다(`files.py` 가 시험 자료 폴더로 복사). 생성기를 시험 때마다 돌리지 않는다.
「3행×4열」은 머리글을 포함한 행 수로 읽었다(IM-009 「표 1개(3행×4열: 항목·검토자·결과·비고)」).

## 확인한 것 (2026-11-11)

- `FileHeader` 서명 `HWP Document File`, 판 5.1.1.0. TD-DOC-12 속성 0b01(압축), TD-DOC-15 속성
  0b11(압축 + **암호**). 암호 비트는 HWP 5.0 문서 형식의 FileHeader 속성 bit 1 이다.
- 한글로 다시 열어 쪽 수 2쪽(TD-DOC-12·13, `check_hwp.ps1`).
- `hwp-hwpx-parser` 1.0.0 으로 TD-DOC-12·13 의 문단 3개와 표 3행×4열이 그대로 나온다. TD-DOC-15 는
  「Encrypted files are not supported」로 읽지 못한다(암호 문서라는 뜻).
- HWP·HWPX 파일 안에는 쪽 수가 없다(HWP 요약 정보 PageCount 0, HWPX 에도 전체 쪽 수 항목 없음).
  쪽 수는 한글이 배치할 때 정해진다. 그래서 제품은 HWP·HWPX 의 쪽 수를 내지 않는다.

## 다시 만들기

한컴오피스 한글(자동화 개체 `HWPFrame.HwpObject`)이 깔린 Windows 에서:

```
powershell -ExecutionPolicy Bypass -File tests\fixtures\im009\hwp\make_hwp.ps1
powershell -ExecutionPolicy Bypass -File tests\fixtures\im009\hwp\check_hwp.ps1
```

- 파일 경로 접근 보안 모듈(FilePathCheckDLL)은 등록하지 않았다. 등록이 없어도 이 PC(한글 2024)에서는
  저장·열기 확인 창 없이 돌았다. 확인 창이 뜨는 환경이면 한컴 개발자 사이트의 보안 모듈을 등록한다.
- 한글 파일에는 만든 시각·사용자 이름이 요약 정보로 들어간다. 다시 만들면 해시가 바뀐다.
  바뀌면 위 표를 고치고 커밋에 이유를 적는다. 내용은 `make_hwp.ps1` 의 문구가 정한다.
- 스크립트는 BOM 붙은 UTF-8 이어야 Windows PowerShell 5.1 이 한글을 바르게 읽는다.
