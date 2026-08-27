package kr.co.axlink.standard.service;

import java.util.Map;
import kr.co.axlink.integration.port.WorkProductType;

public final class StandardLabels {

  private static final Map<WorkProductType, String> WORK_PRODUCT = Map.ofEntries(
      Map.entry(WorkProductType.STATEMENT_OF_WORK, "업무기술서"),
      Map.entry(WorkProductType.PROJECT_PLAN, "프로젝트 계획서"),
      Map.entry(WorkProductType.PROGRESS_STATUS_RECORD, "진척상태 기록부"),
      Map.entry(WorkProductType.MEETING_RECORD, "회의록"),
      Map.entry(WorkProductType.CHANGE_REQUEST, "변경요청서"),
      Map.entry(WorkProductType.CORRECTION_REGISTER, "시정조치 관리대장"),
      Map.entry(WorkProductType.ACCEPTANCE_RECORD, "검수확인서"),
      Map.entry(WorkProductType.PROJECT_REPOSITORY, "프로젝트 저장소"),
      Map.entry(WorkProductType.REPOSITORY_BACKUP, "저장소 백업"),
      Map.entry(WorkProductType.REQUIREMENTS_SPEC, "요구사항 정의서"),
      Map.entry(WorkProductType.TRACEABILITY_RECORD, "추적성 기록부"),
      Map.entry(WorkProductType.SOFTWARE_DESIGN, "소프트웨어 설계서"),
      Map.entry(WorkProductType.TEST_CASES_PROCEDURES, "시험 케이스·절차"),
      Map.entry(WorkProductType.SOFTWARE_COMPONENT, "소프트웨어 컴포넌트"),
      Map.entry(WorkProductType.SOFTWARE, "소프트웨어"),
      Map.entry(WorkProductType.TEST_REPORT, "시험 보고서"),
      Map.entry(WorkProductType.PRODUCT_OPERATION_GUIDE, "제품 운용 지침서"),
      Map.entry(WorkProductType.SOFTWARE_USER_DOC, "소프트웨어 사용자 문서"),
      Map.entry(WorkProductType.SOFTWARE_CONFIGURATION, "소프트웨어 형상"),
      Map.entry(WorkProductType.MAINTENANCE_DOC, "유지보수 문서"),
      Map.entry(WorkProductType.VERIFICATION_RESULTS, "검증 결과"),
      Map.entry(WorkProductType.VALIDATION_RESULTS, "확인 결과"));

  private StandardLabels() {}

  public static String workProduct(WorkProductType type) {
    return type == null ? null : WORK_PRODUCT.getOrDefault(type, type.name());
  }
}
