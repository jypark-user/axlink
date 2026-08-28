insert into app_user (id, organization_id, email, name, password_hash, role, status)
select 'd0000000-0000-4000-8000-000000000001'::uuid, u.organization_id, 'r1', '운영자(개발용)',
       '$2a$10$LZPHAn5UcQw7qDcgjikYYOpy9HvU9BXWJIwF5t5hWvoTuO2kNDI1K', 'SUPER_ADMIN', 'ACTIVE'
  from app_user u
 where u.email = 'admin@axlink.co.kr'
   and not exists (select 1 from app_user where email = 'r1');

insert into app_user (id, organization_id, email, name, password_hash, role, status)
select 'd0000000-0000-4000-8000-000000000002'::uuid, u.organization_id, 'r2', '발주사(개발용)',
       '$2a$10$LZPHAn5UcQw7qDcgjikYYOpy9HvU9BXWJIwF5t5hWvoTuO2kNDI1K', 'CLIENT', 'ACTIVE'
  from app_user u
 where u.email = 'client@axlink.co.kr'
   and not exists (select 1 from app_user where email = 'r2');

insert into app_user (id, organization_id, email, name, password_hash, role, status)
select 'd0000000-0000-4000-8000-000000000003'::uuid, u.organization_id, 'r3', '용역사(개발용)',
       '$2a$10$LZPHAn5UcQw7qDcgjikYYOpy9HvU9BXWJIwF5t5hWvoTuO2kNDI1K', 'CONTRACTOR', 'ACTIVE'
  from app_user u
 where u.email = 'contractor@axlink.co.kr'
   and not exists (select 1 from app_user where email = 'r3');

insert into project_assignment (id, project_id, contractor_org_id, user_id, permissions_json,
                                assigned_by_user_id)
select 'd0000000-0000-4000-8000-000000000004'::uuid, a.project_id, a.contractor_org_id,
       (select id from app_user where email = 'r3'), a.permissions_json, a.assigned_by_user_id
  from project_assignment a
 where a.user_id = (select id from app_user where email = 'contractor@axlink.co.kr')
   and not exists (select 1 from project_assignment
                    where user_id = (select id from app_user where email = 'r3'))
 limit 1;
