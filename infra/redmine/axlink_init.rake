# Redmine 로컬 초기화. 구조만 만든다 — 이슈 내용은 사람이 넣는다.
#
# 실행:
#   docker cp infra/redmine/axlink_init.rake axlink-redmine:/usr/src/redmine/lib/tasks/
#   docker exec -e SECRET_KEY_BASE=change-me-in-local-env axlink-redmine bin/rake axlink:init
#
# rails runner 가 아니라 rake 인 이유 — production 에서 runner 는 eager load 를 하는데,
# 이 이미지의 tzinfo 2.0.6 이 Ruby 3.4 의 시간대 전체 파싱에서 죽는다. rake 는 eager load
# 를 하지 않는다. 몇 번을 다시 돌려도 같은 결과다(멱등).
#
# 매핑 근거는 작업 규약 §2 — Version = 마일스톤(M1~M6), Issue relations = 추적관계,
# 커스텀 필드 REQ ID = 도구를 가로지르는 접착제.

namespace :axlink do
  desc "AX Link 샘플 원천 초기화 (구조만)"
  task init: :environment do

    # ── 1. admin 계정 (로컬 개발 전용 비밀번호)
    admin = User.find_by_login("admin")
    admin.password = admin.password_confirmation = "axlink-admin"
    admin.must_change_passwd = false
    admin.save!

    # ── 2. REST API 활성화 — 기본 비활성이라 커넥터가 붙지 못한다 (ARC-003 §3)
    Setting.rest_api_enabled = "1"
    Setting.default_language = "ko"

    # ── 3. 기본 데이터(상태·역할·워크플로)가 없으면 한국어판으로 로드
    Redmine::DefaultData::Loader.load("ko") if Tracker.count.zero?

    # ── 4. 트래커: 작업 · 결함 · 리스크  (기본 로드의 기능→작업, 버그→결함을 재활용)
    Tracker.find_by_name("새기능")&.update!(name: "작업")
    Tracker.find_by_name("버그")&.update!(name: "결함")
    if Tracker.find_by_name("리스크").nil?
      src = Tracker.find_by_name("작업") || Tracker.first
      risk = Tracker.new(name: "리스크", default_status_id: src.default_status_id)
      risk.save!
      WorkflowRule.copy(src, nil, [risk], nil)   # 워크플로가 없으면 상태 전이가 안 된다
    end

    # ── 5. 커스텀 필드 REQ ID — 모든 트래커에 부여
    cf = IssueCustomField.find_by_name("REQ ID") || IssueCustomField.new(
      name: "REQ ID", field_format: "string", is_filter: true, searchable: true
    )
    cf.is_for_all = true
    cf.trackers = Tracker.all
    cf.save!

    # ── 6. 프로젝트 + 버전(마일스톤 M1~M6)
    project = Project.find_by_identifier("axlink") || Project.create!(
      identifier: "axlink",
      name: "AX Link",
      description: "2026 AX 프로젝트 관리 운영 프레임워크 — 자기참조 1번 사업",
      is_public: false,
    )
    project.trackers = Tracker.all
    project.save!

    {
      "M1 범위·평가기준 확정" => "2026-08-29",
      "M2 연계·수집 기반 확보" => "2026-09-12",
      "M3 통합 현황 시연" => "2026-09-30",
      "M4 통합 PoC 완성" => "2026-10-23",
      "M5 최종보고" => "2026-11-13",
      "M6 최종 인도" => "2026-11-30",
    }.each do |name, due|
      v = project.versions.find_by(name: name) || Version.new(project: project, name: name)
      v.effective_date = Date.parse(due)
      v.save!
    end

    # ── 7. admin API 키 — 커넥터 연결에 쓴다. 저장소에는 기록하지 않는다
    token = Token.find_by(user_id: admin.id, action: "api") || Token.create!(user: admin, action: "api")
    puts "REDMINE_URL=http://localhost:3000"
    puts "REDMINE_PROJECT=axlink"
    puts "REDMINE_ADMIN=admin / axlink-admin (로컬 전용)"
    puts "REDMINE_API_KEY=#{token.value}"
  end
end
