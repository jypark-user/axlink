-- 받는 문서 형식을 넓힌다 (SWFR.CON.007). 코드는 PPTX·MD·TXT 를 읽는데 표의 제약이 옛
-- 5종에 묶여 있어 올리면 500 이 났다(09.23 착수보고 pptx). 제약과 코드의 목록은 같아야 한다.

alter table document_upload drop constraint ck_document_upload__file_ext;
alter table document_upload add constraint ck_document_upload__file_ext
  check (file_ext in ('HWP','HWPX','DOCX','XLSX','PPTX','PDF','MD','TXT'));
