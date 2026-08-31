-- 로그인 식별자를 이메일에서 아이디로 바꾼다.
--
-- 메일을 보내는 코드가 없다. 초대도 링크 전달 방식이라(V6) 주소가 필요 없고,
-- 요구사항에도 이메일 계정을 요구하는 항목이 없다. 형식만 강요하고 있었다.
-- V4 가 개발 계정을 r1·r2·r3 로 만들었다가 V5 에서 @admin.com 을 붙인 것도
-- 검증기에 맞추느라 한 일이다. 되돌린다.
--
-- 컬럼은 varchar(254) 그대로 둔다. 이메일 주소를 아이디로 쓰는 것도 계속 된다.
alter table app_user rename column email to username;
alter index uq_app_user__email rename to uq_app_user__username;

update app_user
   set username = split_part(username, '@', 1), updated_at = now()
 where username in ('r1@admin.com', 'r2@admin.com', 'r3@admin.com');
