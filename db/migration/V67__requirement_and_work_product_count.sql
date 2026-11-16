-- 요구사항 건수·산출물 건수 지표 (PoC 보완 F-11, 2026-11-16 인포 템플릿 검토).
--
-- 구성비 그림(도넛·상태 흐름 등)은 건수를 나눠 그려야 한다. 그런데 요구사항과 산출물에는 비율
-- 지표(이행률·승인률)만 있어서, 예시 위젯 「우선순위별 요구사항 비중」「요구사항 단계 분포」가
-- 이행률을 구성비로 그렸다. 도넛 가운데에 이행률을 더한 값이 합계로 찍히고, 상태 흐름은 상태별
-- 이행률(0 또는 100)이라 띠가 VERIFIED·ACCEPTED 로만 갈렸다. 건수 지표를 더해 바로잡는다.
--
-- 범위는 짝이 되는 비율 지표와 같다. 요구사항은 이행률과 같은 기준선 범위, 산출물은 승인률과
-- 같은 현행·적용 대상 항목이다. 그래야 「건수」와 「비율」이 같은 모집단을 말한다.

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis) values
('requirement_count', '요구사항 건수',
 '요구사항 수. 상태·우선순위별로 몇 건인지, 구성비를 볼 때 쓴다. "요구사항이 몇 건", "단계별 요구사항" 질문에 사용',
 'requirement', null,
 '(e.baseline_id is not null or not exists (select 1 from requirement_baseline rb where rb.project_id = e.project_id and rb.status = ''CONFIRMED''))',
 'count(*)', 'COUNT', '건',
 '{project,contractor_org,requirement_priority,requirement_status,period_month,period_day}',
 '{project_id__in,requirement_priority__in,requirement_status__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'requirement_status', 'ACTIVE',
 '요구사항 이행률과 같은 범위의 요구사항 수다. 확정된 요구사항 기준선이 있으면 그 기준선의 요구사항만, '
 '없으면 그 사업의 요구사항 전부를 센다. 상태별로 나눌 때는 이행률이 분자를 셀 때 보는 상태와 같은 값을 쓴다.'),

('work_product_count', '산출물 건수',
 '산출물 항목 수(현행 버전, 적용 대상). 상태·유형·활동별로 몇 건인지 볼 때 쓴다. "산출물이 상태별로 몇 건" 질문에 사용',
 'work_product', null, 'e.is_current and e.applicable',
 'count(*)', 'COUNT', '건',
 '{project,work_product_type,iso_activity,work_product_status}',
 '{project_id__in,work_product_type__in,work_product_status__in,iso_activity__in}',
 'work_product_status', 'ACTIVE',
 '산출물 승인률과 같은 범위의 항목 수다. 유형마다 현행 버전 하나를 세고, 적용 대상이 아닌 유형은 뺀다. '
 '상태가 「없음」이면 아직 낸 것이 없는 항목이다. WBS 작업별 산출물(WBS 산출물 판정)과는 다른 축이다.');

-- 이미 저장된 위젯 바로잡기. 프리셋으로 만든 「우선순위별 요구사항 비중」(도넛)·「요구사항 단계 분포」
-- ·「산출물 상태 분포」(상태 흐름)가 비율 지표를 담고 있다(11-16 조회: 5174 도넛 4·상태 흐름 4,
-- 5173 각 1). 제목·차원·의도는 그대로 두고 지표만 같은 모집단의 건수로 바꾼다. 두 건수 지표는
-- 짝이 되는 비율 지표와 받는 차원이 같아서 차원은 손대지 않아도 된다. 다른 템플릿·지표는 건드리지
-- 않는다.
update widget
   set spec_json = jsonb_set(spec_json, '{query,measure}', '"requirement_count"'),
       updated_at = now()
 where template in ('DONUT_CHART', 'STATUS_FLOW')
   and spec_json->'query'->>'measure' = 'requirement_fulfillment_rate';

update widget
   set spec_json = jsonb_set(spec_json, '{query,measure}', '"work_product_count"'),
       updated_at = now()
 where template in ('DONUT_CHART', 'STATUS_FLOW')
   and spec_json->'query'->>'measure' = 'work_product_approval_rate';
