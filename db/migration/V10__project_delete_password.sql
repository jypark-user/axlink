-- 사업 삭제 비밀번호. 등록할 때 정하고, 삭제할 때 맞춰야 지워진다.
-- 기존 사업은 값이 없어 삭제할 수 없다 — 비밀번호를 정한 사업만 지운다.
alter table project add column delete_password_hash text;
