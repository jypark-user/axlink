# IM-009 시험자료 PDF (가상 시험자료)

이 폴더의 PDF 세 건은 AX Link 검증용으로 만든 **가상 시험자료**다. 실제 계약 문서·명세서가 아니다.
쪽마다 머리에 「가상 시험자료 · 실제 계약 문서가 아님」을 찍었다.

| 자료 | 파일 | 쪽 | 내용(IM-009) | SHA-256 |
|---|---|---|---|---|
| TD-DOC-4 | 과업지시서.pdf | 3 | 1쪽 개요 / 2쪽 「2. 납품 산출물」 「납품 산출물은 22종이다」 / 3쪽 「3. 사업 기간」 「사업 기간은 9개월이다」. 「사업 기간」은 3쪽에만 있다 | `658f7b460663650bcd8237daee8aff02721e1e4a5d09dc29ac36771a049f0fcd` |
| TD-DOC-7 | 카드형-명세서.pdf | 1 | 표 없이 카드 3장. 코드(UR.CARD.001~003)는 「카드 식별:」 뒤에 있어 줄 머리에 없다 | `2bee4fbdc8e472788ccaa1f45e711cc5d56e2c3bfb04470628b1ce19c69d07ef` |
| TD-DOC-16 | 스캔문서.pdf | 1 | 글자 층 없는 그림 PDF. TD-DOC-4 1쪽을 150dpi 흑백 그림으로 렌더링해 다시 쌌다(`make_scan_pdf.py`). 쪽 머리의 「가상 시험자료」 표시가 그림에 그대로 있다 | `49322fa09faaa659215e0f180711a1da370613a74714a6fc109fb14eb1f78e7c` |

시험은 이 PDF 를 그대로 쓴다(`files.py` 가 시험 자료 폴더로 복사). 생성기를 시험 때마다 돌리지 않는다.

TD-DOC-16 확인(2026-11-11): pdfplumber 로 쪽 1·글자 0·그림 1. 손상 파일이 아니라 정상 PDF 이고,
다시 만들면 같은 해시가 나온다(생성 시각을 넣지 않는다). `python tests/fixtures/im009/pdf/make_scan_pdf.py`
(pypdfium2·Pillow). 과업지시서.pdf 를 바꾸면 이 파일도 다시 만든다.

## 확인한 것 (2026-11-10)

- 두 파일 모두 글자가 뽑힌다(pdfplumber). 손상 파일이나 그림만 있는 PDF 가 아니다.
- 제품 명세서 추출(`app.document.structuring.spec_items`)로 TD-DOC-7 은 **0건**이다. 코드가 줄 머리에
  없어서다. 0건을 만들려고 자료를 바꾸지 않았다(UC-020-S02 의 전제와 그대로 맞는다).
- TD-DOC-4 를 명세서로 읽으면 0건이다(요구사항 명세서가 아니다).
- TD-DOC-4 를 색인하면 3쪽 머리 표시가 앞 절(2. 납품 산출물) 조각에 붙어 그 조각의 위치가 「p.2~3」이
  된다. 실제 문서에도 흔한 쪽 머리글이라 자료를 바꾸지 않고 제품 결함 DEF-V045 로 기록했다(UC-060-S01).
- 처음 만든 판은 2쪽에 산출물 이름(프로그램 목록 등)을 적어 UC-060-S15(WBS 3.3 산출물) 검색과 겹쳤다.
  IM-009 에 없는 내용이라 뺐다.

## 다시 만들기

```
pip install reportlab==4.2.5 fonttools
python tests/fixtures/im009/pdf/make_pdfs.py --variable "C:\Windows\Fonts\NotoSansKR-VF.ttf"
```

- 같은 글꼴 파일이면 같은 해시가 나온다(PDF 생성 시각 고정 `invariant=1`, 글꼴 인스턴스 시각 고정).
  해시가 달라지면 위 표를 고치고 바뀐 이유를 커밋에 적는다.
- 만든 사람이 쓴 글꼴 파일: `NotoSansKR-VF.ttf`(Windows 기본 설치, 버전 2.04),
  SHA-256 `018174e8cdd366aff67c8d366c7dc806a7babbe7f2819fc23b00d59f7b8353d0`.
  가변 글꼴이라 굵기 400 정적 인스턴스를 임시 폴더에 만들어 쓴다.

## 글꼴 사용 조건

- **Noto Sans KR**, SIL Open Font License 1.1(글꼴 이름 표 13번: 「licensed under the SIL Open Font
  License, Version 1.1」). 포함 권한 fsType 0(제한 없음). 문서에 넣어 배포해도 된다.
- PDF 에는 쓴 글자만 담은 부분 글꼴이 들어간다. **글꼴 파일 자체는 저장소에 넣지 않는다.**
- 처음 검토한 나눔스퀘어는 글꼴 안 사용 조건이 「NAVER Corporation」뿐이고 포함 권한이 미리보기·인쇄로
  제한(fsType 4)이라 쓰지 않았다.
