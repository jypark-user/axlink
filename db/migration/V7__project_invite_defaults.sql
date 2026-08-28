-- 초대 링크는 고르는 것이 없다. 용역사명은 가입할 때 본인이 적고, 권한은 기본값으로 부여된다.
alter table project_invite drop column contractor_org_id;
alter table project_invite drop column permissions_json;
