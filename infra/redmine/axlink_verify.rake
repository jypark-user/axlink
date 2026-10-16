# Redmine 연동 검증용 시험 프로젝트와 계정. axlink:init 다음에 돌린다(구조는 그쪽이 만든다).
#
# 실행:
#   docker cp infra/redmine/axlink_verify.rake axlink-rm:/usr/src/redmine/lib/tasks/
#   docker exec axlink-rm sh -c 'SECRET_KEY_BASE="$REDMINE_SECRET_KEY_BASE" \
#     AXLINK_SECRETS_OUT=/tmp/axlink-verify.env bin/rake axlink:verify'
#   docker cp axlink-rm:/tmp/axlink-verify.env <저장소 밖> && docker exec axlink-rm rm /tmp/axlink-verify.env
#
# 계정을 셋으로 나눈다.
#   admin         axlink:init 이 정한 알려진 비밀번호를 무작위로 바꾼다. 평소에는 쓰지 않는다
#   rm-prep       데이터 준비. 시험 프로젝트의 관리자 역할
#   rm-collector  AX Link 수집. 시험 프로젝트에서 이슈 보기만 되는 역할
#   rm-dev        담당자 변경 시험용. 개발자 역할, API 키 없음
# 비밀번호·API 키는 화면에 찍지 않고 AXLINK_SECRETS_OUT 파일에만 쓴다. 다시 돌리면 새 값이 된다.

namespace :axlink do
  desc "AX Link 연동 검증용 시험 프로젝트와 계정"
  task verify: :environment do
    out = ENV.fetch("AXLINK_SECRETS_OUT")
    secrets = {}
    random = -> { SecureRandom.urlsafe_base64(18) }

    admin = User.find_by_login("admin")
    admin.password = admin.password_confirmation = (secrets["REDMINE_ADMIN_PASSWORD"] = random.call)
    admin.must_change_passwd = false
    admin.save!

    # 수집 전용 역할: 이슈 보기만. 수정·댓글·관계 편집 권한은 주지 않는다
    collect_role = Role.find_by_name("수집 읽기") || Role.new(name: "수집 읽기")
    collect_role.permissions = [:view_issues]
    collect_role.issues_visibility = "all"
    collect_role.assignable = false
    collect_role.save!

    givable = Role.givable.sorted.to_a
    manager = givable.find { |r| r.has_permission?(:manage_issue_relations) && r.has_permission?(:edit_issues) } || givable.first
    developer = givable.find { |r| r != manager && r.assignable? && r.has_permission?(:edit_issues) } || manager

    users = {
      "rm-prep" => ["시험", "데이터준비", manager],
      "rm-collector" => ["시험", "수집", collect_role],
      "rm-dev" => ["시험", "개발자", developer],
    }

    project = Project.find_by_identifier("axlink-verify") || Project.create!(
      identifier: "axlink-verify",
      name: "[시험] AX Link 연동 검증",
      description: "AX Link Redmine 연동 검증용 시험 프로젝트. 실제 사업 데이터가 아니다.",
      is_public: false,
    )
    project.trackers = Tracker.all
    project.issue_custom_fields = IssueCustomField.where(name: "REQ ID").to_a
    project.enabled_module_names = %w[issue_tracking files]
    project.save!

    users.each do |login, (first, last, role)|
      u = User.find_by_login(login) || User.new(login: login, firstname: first, lastname: last,
                                                mail: "#{login}@axlink-verify.invalid")
      u.firstname, u.lastname = first, last
      u.password = u.password_confirmation = (secrets["#{login.upcase.tr('-', '_')}_PASSWORD"] = random.call)
      u.must_change_passwd = false
      u.status = User::STATUS_ACTIVE
      u.save!
      member = Member.find_by(project: project, user: u) || Member.new(project: project, user: u)
      member.role_ids = [role.id]
      member.save!
      next if login == "rm-dev"

      Token.where(user_id: u.id, action: "api").delete_all
      secrets["#{login.upcase.tr('-', '_')}_API_KEY"] = Token.create!(user: u, action: "api").value
    end

    {
      "M1 범위·평가기준 확정" => "2026-08-29",
      "M2 연계·수집 기반 확보" => "2026-09-12",
      "M3 통합 현황 시연" => "2026-09-30",
      "M4 통합 PoC 완성" => "2026-10-23",
    }.each do |name, due|
      v = project.versions.find_by(name: name) || Version.new(project: project, name: name)
      v.effective_date = Date.parse(due)
      v.save!
    end

    File.open(out, "w", 0o600) do |f|
      f.puts "REDMINE_URL=http://127.0.0.1:3000"
      f.puts "REDMINE_PROJECT=axlink-verify"
      secrets.each { |k, v| f.puts "#{k}=#{v}" }
    end
    puts "시험 프로젝트·계정 준비 완료 (비밀값은 #{out})"
  end

  # 같은 계정·역할로 시험 프로젝트를 하나 더 만든다. 비밀번호·키는 바꾸지 않는다.
  #   AXLINK_PROJECT=axlink-verify-b AXLINK_PROJECT_NAME="[시험] ..." bin/rake axlink:verify_project
  desc "AX Link 연동 검증용 시험 프로젝트 추가"
  task verify_project: :environment do
    ident = ENV.fetch("AXLINK_PROJECT")
    project = Project.find_by_identifier(ident) || Project.create!(
      identifier: ident, name: ENV.fetch("AXLINK_PROJECT_NAME"),
      description: "AX Link Redmine 연동 검증용 시험 프로젝트. 실제 사업 데이터가 아니다.",
      is_public: false,
    )
    project.trackers = Tracker.all
    project.issue_custom_fields = IssueCustomField.where(name: "REQ ID").to_a
    project.enabled_module_names = %w[issue_tracking files]
    project.save!
    base = Project.find_by_identifier("axlink-verify")
    base.members.each do |m|
      member = Member.find_by(project: project, user: m.user) || Member.new(project: project, user: m.user)
      member.role_ids = m.role_ids
      member.save!
    end
    base.versions.each do |bv|
      v = project.versions.find_by(name: bv.name) || Version.new(project: project, name: bv.name)
      v.effective_date = bv.effective_date
      v.save!
    end
    puts "#{ident} 준비 완료"
  end
end
