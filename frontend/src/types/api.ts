export const WORK_PRODUCT_TYPES = [
  'STATEMENT_OF_WORK',
  'PROJECT_PLAN',
  'PROGRESS_STATUS_RECORD',
  'MEETING_RECORD',
  'CHANGE_REQUEST',
  'CORRECTION_REGISTER',
  'ACCEPTANCE_RECORD',
  'PROJECT_REPOSITORY',
  'REPOSITORY_BACKUP',
  'REQUIREMENTS_SPEC',
  'TRACEABILITY_RECORD',
  'SOFTWARE_DESIGN',
  'TEST_CASES_PROCEDURES',
  'SOFTWARE_COMPONENT',
  'SOFTWARE',
  'TEST_REPORT',
  'PRODUCT_OPERATION_GUIDE',
  'SOFTWARE_USER_DOC',
  'SOFTWARE_CONFIGURATION',
  'MAINTENANCE_DOC',
  'VERIFICATION_RESULTS',
  'VALIDATION_RESULTS',
] as const;

export type WorkProductType = (typeof WORK_PRODUCT_TYPES)[number];

export const SI_PHASES = ['SI_1', 'SI_2', 'SI_3', 'SI_4', 'SI_5', 'SI_6'] as const;
export type SiPhase = (typeof SI_PHASES)[number];

export const PM_ACTIVITIES = ['PM_1', 'PM_2', 'PM_3', 'PM_4'] as const;
export type PmActivity = (typeof PM_ACTIVITIES)[number];

export type Role = 'SUPER_ADMIN' | 'CLIENT' | 'CONTRACTOR';
export type OrgType = 'CLIENT' | 'CONTRACTOR';
export type OrgStatus = 'ACTIVE' | 'DISABLED';
export type UserStatus = 'INVITED' | 'ACTIVE' | 'DISABLED';
export type ProjectStatus = 'PLANNING' | 'ACTIVE' | 'CLOSING' | 'CLOSED';
export type AssignmentStatus = 'ACTIVE' | 'REVOKED';
export type ToolKind = 'GITHUB' | 'REDMINE';
export type ConnectionStatus = 'DRAFT' | 'VERIFIED' | 'ACTIVE' | 'PAUSED' | 'FAILED';
export type SyncJobKind = 'BACKFILL' | 'POLL' | 'WEBHOOK';
export type SyncJobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
export type SourceKind = 'TOOL' | 'DOCUMENT' | 'MANUAL';
export type RequirementStatus =
  'DEFINED' | 'DESIGNED' | 'IMPLEMENTED' | 'VERIFIED' | 'ACCEPTED' | 'REJECTED';
export type IssueStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';
export type WorkProductStatus = 'NONE' | 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED';
export type RiskStatus = 'OPEN' | 'MITIGATING' | 'CLOSED';
export type ChangeRequestStatus = 'REQUESTED' | 'REVIEWING' | 'APPROVED' | 'REJECTED' | 'APPLIED';
export type CorrectionActionStatus = 'OPEN' | 'DONE' | 'OVERDUE';
export type Priority = 'MUST' | 'SHOULD' | 'COULD' | 'WONT';
export type IssueSeverity = 'BLOCKER' | 'CRITICAL' | 'MAJOR' | 'MINOR' | 'TRIVIAL';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type TraceEntityType =
  | 'REQUIREMENT'
  | 'ISSUE'
  | 'WORK_PRODUCT'
  | 'RISK'
  | 'CODE_CHANGE'
  | 'CHANGE_REQUEST'
  | 'CORRECTION_ACTION'
  /** 저장소 설계 문서(수집한 원본). 등록 산출물(WORK_PRODUCT)과 다르다 (ARC-024) */
  | 'REPO_DOCUMENT';
export type TraceLinkKind = 'DESIGNS' | 'IMPLEMENTS' | 'TESTS' | 'DELIVERS';
export type TraceLinkOrigin = 'AUTO' | 'MANUAL';
/** SUPERSEDED 는 분류 정정으로 대체·제외됨, BROKEN 은 원천 근거가 사라짐 */
export type TraceLinkStatus = 'ACTIVE' | 'BROKEN' | 'SUPERSEDED';
export type CodeChangeKind = 'COMMIT' | 'MERGE_REQUEST' | 'PIPELINE' | 'RELEASE' | 'TAG';
export type AcceptanceRecordStatus = 'ISSUED' | 'VOIDED';
export type DocumentStatus =
  'UPLOADED' | 'EXTRACTED' | 'STRUCTURED' | 'CONFIRMED' | 'REJECTED' | 'FAILED';
export type StructuringDraftStatus = 'PROPOSED' | 'CONFIRMED' | 'REJECTED' | 'MANUAL_OVERRIDE';
export type ChunkSourceType =
  | 'WORK_PRODUCT'
  | 'REQUIREMENT'
  | 'ISSUE'
  | 'RISK'
  | 'CHANGE_REQUEST'
  | 'CORRECTION_ACTION'
  | 'MEETING_RECORD'
  | 'PROGRESS_RECORD'
  | 'DOCUMENT_UPLOAD';
export type MessageRole = 'USER' | 'ASSISTANT';
export type MessageFeedback = 'UP' | 'DOWN';
export type RouteType = 'DOCUMENT' | 'AGGREGATE' | 'MIXED' | 'OVERVIEW' | 'INTENT' | 'CLARIFY';
export type WidgetTemplate =
  | 'STAT_CARD'
  | 'BAR_CHART'
  | 'LINE_CHART'
  | 'PIE_CHART'
  | 'PROGRESS_LIST'
  | 'DATA_TABLE'
  | 'CHECKLIST'
  | 'GANTT_SUMMARY'
  | 'STATUS_FLOW'
  | 'HEATMAP'
  | 'AREA_CHART'
  | 'STACKED_BAR_CHART'
  | 'HORIZONTAL_BAR_CHART'
  | 'DONUT_CHART'
  | 'RADAR_CHART'
  | 'CUMULATIVE_FLOW'
  | 'PARETO'
  | 'TREEMAP'
  | 'SLOPE_CHART'
  | 'BUMP_CHART'
  | 'SPARKLINE'
  | 'BULLET_CHART'
  | 'CALENDAR_HEATMAP';
export type MappingSourceKind = 'ISSUE_TYPE' | 'OBJECT_KIND' | 'TRACKER';
export type MappingTargetEntity =
  'REQUIREMENT' | 'ISSUE' | 'RISK' | 'WORK_PRODUCT' | 'TRACE_LINK' | 'PROGRESS_RECORD';
export type FilterOp = 'IN' | 'EQ' | 'BETWEEN' | 'IN_MONTH' | 'LAST_N_DAYS' | 'GTE' | 'LTE';
export type CatalogStatus = 'ACTIVE' | 'DEPRECATED';
export type MeasureValueType = 'COUNT' | 'RATE_PCT' | 'DAYS' | 'PCT_POINT';
export type DimensionValueType = 'CATEGORY' | 'TIME';
export type FilterValueType = 'ENUM_LIST' | 'UUID_LIST' | 'DATE_RANGE' | 'MONTH_TOKEN' | 'INT';

export interface PageResponse<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
  hasNext: boolean;
}

export interface ErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
  path: string;
  timestamp: string;
}

export interface FieldError {
  field: string;
  reason: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshTokenRequest {
  refreshToken: string;
}

export interface RefreshResponse {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: MeResponse;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: MeResponse;
}

export interface MeResponse {
  userId: string;
  username: string;
  name: string;
  role: Role;
  organizationId: string;
  organizationName: string;
  organizationType: OrgType;
  allowedProjectIds: string[];
}

export type InviteKind = 'PROJECT' | 'USER';

export interface InvitationPreviewResponse {
  kind: InviteKind;
  projectName: string | null;
  organizationName: string;
  username: string | null;
  name: string | null;
  expiresAt: string;
  /** 업체를 지정한 사업 초대면 그 업체 이름. 가입자는 이 업체로만 들어간다 */
  contractorOrgName?: string | null;
}

/** contractorOrgName·username·name은 PROJECT 초대에만 필요하다. */
export interface AcceptInvitationRequest {
  token: string;
  contractorOrgName?: string;
  username?: string;
  name?: string;
  password: string;
}

export interface UserInviteLinkResponse {
  token: string;
  expiresAt: string;
}

export interface ProjectInviteResponse {
  id: string;
  projectId: string;
  expiresAt: string;
  revokedAt: string | null;
  createdAt: string;
  /** 생성 응답에만 담긴다. 목록 조회에서는 null. */
  token: string | null;
  organizationId?: string | null;
  organizationName?: string | null;
}

export interface OrganizationCreateRequest {
  name: string;
  type: OrgType;
  businessNo: string | null;
}

export interface OrganizationUpdateRequest {
  name: string | null;
  businessNo: string | null;
}

export interface OrganizationResponse {
  id: string;
  name: string;
  type: OrgType;
  businessNo: string | null;
  userCount: number;
  projectCount: number;
  createdAt: string;
}

export interface UserCreateRequest {
  organizationId: string;
  username: string;
  name: string;
  role: Role;
}

export interface UserUpdateRequest {
  name: string | null;
  role: Role | null;
  status: UserStatus | null;
}

export interface UserResponse {
  id: string;
  organizationId: string;
  organizationName: string;
  username: string;
  name: string;
  role: Role;
  status: UserStatus;
  lastLoginAt: string | null;
  createdAt: string;
}

/** 최고관리자 화면의 조직(GH-187). 발주기관은 여기서 만들고, 용역사는 초대 가입으로 생긴다 */
export interface OrganizationResponse {
  id: string;
  name: string;
  type: 'CLIENT' | 'CONTRACTOR';
  status: 'ACTIVE' | 'DISABLED';
  userCount: number;
  activeUserCount: number;
  projectCount: number;
  createdAt: string;
}

/** 발급한 발주기관 계정. 첫 비밀번호는 이 응답에만 있다 */
export interface ClientUserCreatedResponse {
  id: string;
  organizationId: string;
  username: string;
  name: string;
  role: Role;
  status: UserStatus;
  temporaryPassword: string;
}

export interface ProjectCreateRequest {
  name: string;
  startDate: string;
  endDate: string;
  description: string;
  contractorName: string;
  /** 이 사업을 지울 때 맞춰야 하는 비밀번호. 서버는 해시로만 갖고 있는다. */
  deletePassword: string;
}

export interface ProjectDeleteRequest {
  password: string;
}

export interface ProjectUpdateRequest {
  name: string | null;
  startDate: string | null;
  endDate: string | null;
  description: string | null;
  contractorName: string | null;
  currentSiPhase: SiPhase | null;
}

export interface ProjectSummaryResponse {
  id: string;
  name: string;
  status: ProjectStatus;
  startDate: string;
  endDate: string;
  currentSiPhase: SiPhase;
  clientOrgId: string;
  clientOrgName: string;
  contractorName: string | null;
  requiredWorkProductApproved: number;
  requiredWorkProductTotal: number;
  openCorrectionActionCount: number;
  openRiskCount: number;
  /** 미처리 확인 요청. 확인완료가 아닌 것 (SWFR.WEB.006). */
  openReviewRequestCount: number;
  /** 대표 진척률(0~1). 현황 화면과 같은 산정. 산출 불가면 null. */
  representative: number | null;
  progressLevel: string | null;
  /** WBS 실적 − 계획선(0~1 차이). WBS 가 없으면 null. */
  progressDeviation: number | null;
  updatedAt: string;
}

export interface ProjectMetrics {
  requirementTotal: number;
  requirementAccepted: number;
  issueOpen: number;
  riskOpen: number;
  workProductApproved: number;
  workProductTotal: number;
  traceabilityCoverage: number;
  lastSyncedAt: string | null;
}

export interface ProjectDetailResponse {
  id: string;
  name: string;
  description: string;
  contractorName: string | null;
  status: ProjectStatus;
  startDate: string;
  endDate: string;
  currentSiPhase: SiPhase;
  clientOrgId: string;
  clientOrgName: string;
  assignmentCount: number;
  connectionCount: number;
  defaultDashboardId: string;
  openReviewRequestCount: number;
  metrics: ProjectMetrics;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectCloseRequest {
  confirmationNote: string | null;
}

export interface ClosureCheck {
  key: 'ACCEPTANCE_RECORD_EXISTS' | 'REQUIRED_WORK_PRODUCTS_APPROVED' | 'NO_OPEN_CORRECTION_ACTION';
  satisfied: boolean;
  detail: string;
}

export interface ProjectClosureResponse {
  projectId: string;
  closable: boolean;
  checks: ClosureCheck[];
}

export interface AssignmentCreateRequest {
  contractorOrgId: string;
  userIds: string[];
}

export interface AssignmentResponse {
  id: string;
  projectId: string;
  contractorOrgId: string;
  contractorOrgName: string;
  userId: string;
  userName: string;
  userEmail: string;
  status: AssignmentStatus;
  assignedAt: string;
}

export interface ToolCredentialRequest {
  accessToken: string;
}

export interface ToolConnectionCreateRequest {
  tool: ToolKind;
  name: string;
  baseUrl: string;
  targetResource: string;
  credential: ToolCredentialRequest;
}

export interface ToolConnectionUpdateRequest {
  name: string | null;
  baseUrl: string | null;
  targetResource: string | null;
  credential: ToolCredentialRequest | null;
}

export interface ToolConnectionStatusUpdateRequest {
  status: Extract<ConnectionStatus, 'ACTIVE' | 'PAUSED'>;
}

export interface ToolConnectionResponse {
  id: string;
  projectId: string;
  tool: ToolKind;
  name: string;
  baseUrl: string;
  targetResource: string;
  /** 인증정보 끝자리. 소유 업체·발주기관·관리자에게만 온다 */
  credentialMasked: string | null;
  status: ConnectionStatus;
  lastSyncedAt: string | null;
  lastSyncStatus: SyncJobStatus | null;
  lastSyncError: string | null;
  ingestedCount: number;
  mappingRuleCount: number;
  createdAt: string;
  ownerOrgId: string | null;
  ownerOrgName: string | null;
  /** PARTICIPANT 참여 업체 · CLIENT 발주기관이 만듦 · UNCLEAR 참여 업체 아님(지정 필요) */
  ownerState: 'PARTICIPANT' | 'CLIENT' | 'UNCLEAR' | null;
  /** 이 사용자가 설정 변경·삭제·연결 테스트를 할 수 있는지 */
  canManage: boolean;
}

/** 사업의 참여 업체(GH-138). 대표사·참여사는 표시 구분이고 권한이 없다. */
export interface ParticipantResponse {
  id: string;
  organizationId: string;
  organizationName: string;
  role: 'REPRESENTATIVE' | 'PARTICIPANT';
  workNote: string | null;
  status: 'ACTIVE' | 'REMOVED';
  userCount: number;
  connectionCount: number;
  createdAt: string;
  removedAt: string | null;
}

export interface ToolConnectionTestRequest {
  tool: ToolKind;
  baseUrl: string;
  targetResource: string;
  credential: ToolCredentialRequest;
}

export interface ToolConnectionTestResponse {
  reachable: boolean;
  resourceName: string;
  detectedItemTypes: string[];
  /** 토큰에 권한이 빠져 읽지 못하는 항목. 연결은 되지만 이 항목은 수집되지 않는다. */
  deniedItemTypes?: string[];
  checkedAt: string;
}

export interface SyncTriggerRequest {
  kind: SyncJobKind;
}

export interface MappingRuleResponse {
  id: string;
  connectionId: string;
  sourceKind: MappingSourceKind;
  sourceValue: string;
  targetEntity: MappingTargetEntity;
  targetWorkProductType: WorkProductType | null;
  statusMap: Record<string, string>;
  enabled: boolean;
}

export interface MappingRuleUpsertRequest {
  sourceKind: MappingSourceKind;
  sourceValue: string;
  targetEntity: MappingTargetEntity;
  targetWorkProductType: WorkProductType | null;
  statusMap: Record<string, string>;
  enabled: boolean;
}

export interface MappingRuleReplaceRequest {
  rules: MappingRuleUpsertRequest[];
  reapply: 'NEXT_POLL' | 'BACKFILL_NOW';
}

export interface SyncJobStats {
  fetched: number;
  /** 새로 생기거나 바뀐 원본 건수. 변경이 없으면 0 */
  changed: number;
  /** 표준 모델로 올린 건수(재승격 포함) */
  upserted: number;
  unmapped: number;
  indexed: number;
  skippedUnchanged: number;
}

export interface SyncJobResponse {
  id: string;
  connectionId: string;
  connectionName: string;
  projectId: string;
  tool: ToolKind;
  kind: SyncJobKind;
  status: SyncJobStatus;
  startedAt: string | null;
  finishedAt: string | null;
  stats: SyncJobStats;
  error: string | null;
  retryable: boolean;
}

export interface EntityStatusUpdateRequest {
  status: string;
  note: string | null;
}

export interface SourceRef {
  tool: ToolKind | 'UPLOAD' | 'MANUAL';
  connectionId: string | null;
  externalId: string | null;
  externalUrl: string | null;
  /** 같은 도구의 연결이 여럿이면 tool 만으로는 어디서 왔는지 모른다(GH-140) */
  connectionName?: string | null;
  /** 저장소(owner/repo)나 Redmine 프로젝트 식별자 */
  target?: string | null;
  /** 원천 번호. externalId 의 종류 접두(issue: 등)를 뗀 것 */
  number?: string | null;
}

export interface EntityHistoryResponse {
  id: string;
  entityType: string;
  entityId: string;
  field: string;
  fromValue: string | null;
  toValue: string | null;
  actor: string;
  actorName: string | null;
  changedAt: string;
}

export interface TraceLinkResponse {
  id: string;
  projectId: string;
  fromType: TraceEntityType;
  fromId: string;
  fromLabel: string;
  toType: TraceEntityType;
  toId: string;
  toLabel: string;
  linkKind: TraceLinkKind;
  origin: TraceLinkOrigin;
  status: TraceLinkStatus;
  /** 근거 유형. 자동 생성 링크에는 반드시 있다. 수기 링크는 null */
  evidenceKind: string | null;
  /** 근거가 적힌 원문 한 줄 */
  evidenceText: string | null;
  /** 근거 원문의 위치(커밋·이슈 링크) */
  externalUrl: string | null;
  createdAt: string;
  /** 근거 위치(설계 문서의 경로·커밋·blob·줄·절·문서 상태) */
  evidenceMeta?: Record<string, unknown> | null;
  /** 대체·제외·끊김의 사유 */
  statusReason?: string | null;
  statusChangedAt?: string | null;
  supersededBy?: string | null;
}

export interface TraceLinkCreateRequest {
  fromType: TraceEntityType;
  fromId: string;
  toType: TraceEntityType;
  toId: string;
  linkKind: TraceLinkKind;
}

export interface TraceCell {
  targetId: string;
  label: string;
  externalUrl: string | null;
  /** 출발점 종류. REPO_DOCUMENT 는 저장소 설계 문서 */
  sourceType?: TraceEntityType | null;
  /** 문서에 선언된 상태. 발주기관 승인과 다르다 */
  docStatus?: 'CONFIRMED' | 'DRAFT' | 'UNKNOWN' | null;
  section?: string | null;
  /** 참조에 붙은 한정어("미결" 등) */
  qualifier?: string | null;
}

export type SourceState = 'OPEN' | 'CLOSED' | 'UNKNOWN' | 'NONE';

export interface StatusCount {
  status: RequirementStatus;
  count: number;
}

/** 연결 하나의 출처 이슈 상태. connectionId 가 null 이면 출처 이슈가 없는 요구사항 묶음이다. */
export interface SourceStateSummary {
  connectionId: string | null;
  tool: string;
  label: string;
  total: number;
  open: number;
  closed: number;
  unknown: number;
}

/** 요구사항 화면 요약. 목록 쪽과 상관없이 사업 전체를 서버가 센다. */
export interface RequirementSummaryResponse {
  total: number;
  /** VERIFIED · ACCEPTED */
  verified: number;
  notVerified: number;
  /** IMPLEMENTED 중 출처 이슈가 닫혀서 붙은 건수. 실제 구현을 확인한 것은 아니다. */
  implementedFromSourceClosed: number;
  /** total 이 0 이면 null */
  verifiedRate: number | null;
  /** 발주기관이 상태를 지정한 요구사항 수 */
  decided: number;
  byStatus: StatusCount[];
  sources: SourceStateSummary[];
}

/** 사용 안내 문서. 원천은 docs/40-manual 의 마크다운이다. */
/** 사용 설명서 목차 한 줄. file 은 문서끼리의 링크가 가리키는 파일 이름이다. */
export interface HelpEntryResponse {
  slug: string;
  title: string;
  file: string;
}

export interface HelpDocResponse {
  slug: string;
  title: string;
  markdown: string;
  updatedAt: string;
}

/** 상태의 출처. SOURCE_ISSUE_CLOSED = GitHub 이슈 닫힘, CLIENT_DECIDED = 발주기관 지정 */
export type RequirementStatusBasis = 'SOURCE_ISSUE_CLOSED' | 'CLIENT_DECIDED';

/** 발주기관이 사유와 함께 지정한 요구사항 상태(ARC-025). 근거 상태와 따로 남는다. */
export interface RequirementDecision {
  status: RequirementStatus;
  reason: string;
  decidedBy: string | null;
  decidedAt: string;
}

export interface TraceabilityRowResponse {
  requirementId: string;
  requirementCode: string;
  requirementTitle: string;
  requirementStatus: RequirementStatus;
  requirementStatusBasis: RequirementStatusBasis | null;
  /** 근거가 정한 상태. 지정이 없으면 requirementStatus 와 같다 */
  requirementEvidenceStatus: RequirementStatus | null;
  requirementDecision: RequirementDecision | null;
  /** 출처 이슈 상태(명세서 전에 이슈로 만든 요구사항만). 출처 이슈가 없으면 NONE. 요구사항 상태와 따로다. */
  sourceState: SourceState;
  designs: TraceCell[];
  implementsList: TraceCell[];
  tests: TraceCell[];
  brokenAt: TraceLinkKind[];
}

export interface RequirementResponse {
  id: string;
  projectId: string;
  code: string;
  title: string;
  priority: Priority;
  status: RequirementStatus;
  assignee: string | null;
  source: SourceRef;
  traceComplete: boolean;
  updatedAt: string;
  statusBasis: RequirementStatusBasis | null;
  evidenceStatus: RequirementStatus | null;
  decision: RequirementDecision | null;
  /** 확정된 요구사항 기준선에 들었는지. 기준선이 없거나 명세서에 없던 코드면 false */
  inBaseline: boolean;
}

/** 요구사항이 들어온 확정 명세서와 그 안의 원문 위치(GH-158). 명세서로 확정한 요구사항만 있다. */
export interface RequirementBaselineSource {
  baselineId: string;
  version: number;
  status: string;
  confirmedAt: string | null;
  confirmedBy: string | null;
  documentId: string | null;
  sourceFilename: string;
  sourceDocVersion: string | null;
  /** 명세서 안 위치("표 3 · 2행") */
  location: string | null;
  /** 확정 때 판정 NEW · SAME · CHANGED */
  match: string | null;
}

export interface RequirementDetailResponse extends RequirementResponse {
  body: string;
  traceLinks: TraceLinkResponse[];
  history: EntityHistoryResponse[];
  baselineSource: RequirementBaselineSource | null;
}

/** 일반 이슈 화면 카드. 목록 쪽과 상관없이 사업 전체를 서버가 센다. */
export interface IssueSummaryResponse {
  total: number;
  open: number;
  closed: number;
  heavyOpen: number;
  unassignedOpen: number;
  /** 열린 것 중 심각도 미지정. 고위험에서 빼고 따로 센다 */
  unspecifiedOpen: number;
  /** 연결 고르기. 연결을 골라 물어도 사업 전체 연결을 낸다 */
  sources: IssueSourceCount[];
}

/** connectionId 가 없으면 도구에서 오지 않은 이슈(업로드·수기)다. */
export interface IssueSourceCount {
  connectionId: string | null;
  tool: ToolKind | null;
  name: string | null;
  target: string | null;
  count: number;
}

export interface IssueResponse {
  id: string;
  projectId: string;
  key: string;
  title: string;
  status: IssueStatus;
  /** null 이면 원천에 심각도 근거가 없다(미지정) */
  severity: IssueSeverity | null;
  /** 원천 우선순위 원문. 심각도와 다르다 */
  sourcePriority?: string | null;
  assignee: string | null;
  resolvedAt: string | null;
  source: SourceRef;
  updatedAt: string;
  /** 원천이 지정한 마일스톤. 없으면 null (ARC-023) */
  milestone: IssueMilestone | null;
  /** Redmine 트래커 이름. GitHub 은 null */
  tracker?: string | null;
  /** 요구사항 ID 커스텀 필드에 적힌 코드 */
  requirementRefs?: string[];
  /** 도구가 만든 이슈관계(출발점 쪽) */
  relations?: IssueRelation[];
}

export interface IssueRelation {
  type: string;
  issueKey: string;
}

/** 원천 마일스톤의 이름·기한·상태. 원천 값 그대로다 */
export interface IssueMilestone {
  title: string;
  /** 기한 YYYY-MM-DD. 원천에 없으면 null */
  dueOn: string | null;
  state: 'OPEN' | 'CLOSED';
  url: string | null;
}

export interface WorkProductResponse {
  id: string;
  projectId: string;
  type: WorkProductType;
  displayName: string;
  title: string | null;
  version: string | null;
  status: WorkProductStatus;
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
  applicable: boolean;
  dueDate: string | null;
  fileUri: string | null;
  externalUrl: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  updatedAt: string;
  /** 지난 버전. 최신이 먼저(AC-031-5). */
  history: WorkProductVersionResponse[];
}

export interface WorkProductVersionResponse {
  id: string;
  version: string | null;
  title: string | null;
  status: WorkProductStatus;
  submittedAt: string | null;
  rejectReason: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
}

export interface WorkProductChecklistResponse {
  projectId: string;
  approvedCount: number;
  totalCount: number;
  items: WorkProductResponse[];
}

export interface WorkProductVersionResponse {
  id: string;
  version: string;
  status: WorkProductStatus;
  approvedAt: string | null;
  createdAt: string;
}

export interface WorkProductDetailResponse extends WorkProductResponse {
  documentId: string | null;
  chunkCount: number;
  versions: WorkProductVersionResponse[];
  history: EntityHistoryResponse[];
}

export interface WorkProductStatusUpdateRequest {
  status: WorkProductStatus;
  note: string | null;
}

export interface RiskResponse {
  id: string;
  projectId: string;
  title: string;
  probability: RiskLevel;
  impact: RiskLevel;
  severity: RiskLevel;
  mitigation: string | null;
  status: RiskStatus;
  source: SourceRef;
  updatedAt: string;
}

export interface ChangeRequestResponse {
  id: string;
  projectId: string;
  code: string;
  title: string;
  reason: string;
  impactSummary: string | null;
  status: ChangeRequestStatus;
  source: SourceRef;
  updatedAt: string;
}

export interface CorrectionActionResponse {
  id: string;
  projectId: string;
  code: string;
  finding: string;
  action: string;
  owner: string | null;
  dueDate: string | null;
  status: CorrectionActionStatus;
  overdueDays: number;
  updatedAt: string;
}

export interface ProgressRecordResponse {
  id: string;
  projectId: string;
  period: string;
  plannedPct: number;
  actualPct: number;
  summary: string | null;
  source: SourceRef;
}

export interface AcceptanceRecordCreateRequest {
  acceptedBy: string;
  acceptedAt: string;
  conditions: string | null;
  documentId: string | null;
}

export interface AcceptanceRecordResponse {
  id: string;
  projectId: string;
  acceptedBy: string;
  acceptedAt: string;
  conditions: string | null;
  documentUri: string | null;
  status: AcceptanceRecordStatus;
  createdAt: string;
}

/** 확인 요청 · 조치 보고 (SWFR.WEB.004~006). AX Link 안에만 기록한다. */
export type ReviewTargetType = 'WBS_ITEM' | 'WORK_PRODUCT' | 'ISSUE' | 'RISK' | 'METRIC';
export type ReviewRequestStatus = 'REQUESTED' | 'REPORTED' | 'CONFIRMED';
export type ReviewEventKind =
  'REQUESTED' | 'REPORTED' | 'CONFIRMED' | 'REREQUESTED' | 'COMPLETION_WITHDRAWN';

/** GENERAL 은 일반 확인 요청, WBS_COMPLETION 은 WBS 작업 하나의 완료를 확인해 달라는 요청이다. */
export type ReviewPurpose = 'GENERAL' | 'WBS_COMPLETION';

export type EvidenceKind =
  'WORK_PRODUCT' | 'DOCUMENT' | 'FILE' | 'COMMIT' | 'TEST' | 'DEMO' | 'MEETING' | 'OTHER';

/** 완료 근거 한 줄. WORK_PRODUCT 는 등록된 산출물 버전 하나이고 서버가 버전·상태를 채운다. */
export interface EvidenceItem {
  kind: EvidenceKind;
  ref: string;
  note: string;
  workProductId?: string | null;
  version?: string | null;
  statusAtReport?: string | null;
}

/** 완료 확인·철회 한 줄. 확인 당시 값이 고정돼 있다. */
export interface CompletionRecord {
  id: string;
  kind: 'CONFIRMED' | 'WITHDRAWN';
  decidedByName: string;
  decidedAt: string;
  wbsId: string;
  weightAt: number;
  planVersion: string | null;
  reportedActual: number | null;
  completionScope: string;
  evidence: {
    facts?: Record<string, unknown>;
    reported?: EvidenceItem[];
    work_products_at_confirm?: { workProductId: string; version: string | null; status: string }[];
  };
  note: string | null;
}

export type CompletionStatus = 'CONFIRMED' | 'RECONFIRM' | 'WITHDRAWN' | 'NONE';

export interface CompletionItem {
  wbsId: string;
  taskKey: string;
  name: string;
  deliverable: string | null;
  weight: number;
  reportedActual: number | null;
  keyReason: string;
  fileCheck: string | null;
  fileRef: string | null;
  submission: string;
  approval: string;
  productVersion: string | null;
  completionStatus: CompletionStatus;
  predecessorConfirmed: boolean;
  confirmedAt: string | null;
  confirmedBy: string | null;
  weightAtConfirm: number | null;
  planVersionAtConfirm: string | null;
  actualAtConfirm: number | null;
  evidenceRevised: boolean;
  openRequestId: string | null;
  openRequestStatus: ReviewRequestStatus | null;
}

/** 보고 진척률과 완료 확인율. 분모가 없으면 비율은 null(산출 불가). */
export interface CompletionSummaryResponse {
  reportedPct: number | null;
  completionRate: number | null;
  basis: string;
  leafCount: number;
  confirmedCount: number;
  reconfirmCount: number;
  reported100Count: number;
  reported100Pending: number;
  inProgressCount: number;
  items: CompletionItem[];
}

export interface ReviewTargetOption {
  key: string;
  label: string;
}

export interface ReviewRequestCreateRequest {
  targetType: ReviewTargetType;
  targetKey: string;
  title: string;
  body: string;
}

export interface ReviewBodyRequest {
  body: string;
}

/** 요청 시점과 지금의 값 차이. 시스템이 계산한다. */
export interface ReviewStateChange {
  field: string;
  label: string;
  before: unknown;
  after: unknown;
}

export interface ReviewRequestEventResponse {
  id: string;
  kind: ReviewEventKind;
  body: string | null;
  actorName: string;
  snapshot: Record<string, unknown>;
  createdAt: string;
  evidence?: EvidenceItem[] | null;
}

export interface ReviewRequestResponse {
  id: string;
  projectId: string;
  targetType: ReviewTargetType;
  targetKey: string;
  targetLabel: string;
  title: string;
  body: string;
  status: ReviewRequestStatus;
  requestedByName: string;
  requestedAt: string;
  reportBody: string | null;
  reportedByName: string | null;
  reportedAt: string | null;
  confirmedByName: string | null;
  confirmedAt: string | null;
  rerequestCount: number;
  updatedAt: string;
  purpose: ReviewPurpose;
  completionScope: string | null;
}

export interface ReviewRequestDetailResponse extends ReviewRequestResponse {
  snapshot: Record<string, unknown>;
  currentState: Record<string, unknown>;
  changes: ReviewStateChange[];
  events: ReviewRequestEventResponse[];
  completionRecords: CompletionRecord[];
}

export interface GridItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW: number | null;
  minH: number | null;
}

export interface DashboardLayout {
  lg: GridItem[];
  md: GridItem[];
  sm: GridItem[];
}

export interface WidgetFilter {
  field: string;
  op: FilterOp;
  value: unknown;
}

export interface WidgetQuery {
  measure: string;
  dimensions: string[];
  filters: WidgetFilter[];
  projectScope: string[];
  limit: number | null;
}

export interface WidgetThreshold {
  warn: number;
  critical: number;
}

export interface WidgetOptions {
  unit: string | null;
  sort: string | null;
  threshold: WidgetThreshold | null;
  stacked: boolean | null;
  showLegend: boolean | null;
  compareWithPrevious: boolean | null;
  columns: string[] | null;
}

export interface WidgetSpec {
  template: WidgetTemplate;
  title: string;
  query: WidgetQuery;
  options: WidgetOptions | null;
  /** 만들 때 적은 의도. 고칠 때 다시 보여 준다. 값은 query 가 정한다 */
  prompt?: string | null;
}

export interface WidgetColumn {
  key: string;
  label: string;
  type: string;
}

export interface WidgetRow {
  values: Record<string, unknown>;
}

export interface WidgetDataResponse {
  measure: string;
  measureLabel: string;
  unit: string | null;
  dimensions: string[];
  columns: WidgetColumn[];
  rows: WidgetRow[];
  total: WidgetRow | null;
  previousTotal: WidgetRow | null;
  /** 이 지표의 목표값 — 불릿 차트가 기준선을 긋는다. 목표가 없으면 null. */
  target: number | null;
  appliedProjectIds: string[];
  truncated: boolean;
  generatedAt: string;
  /** 이 값이 어떻게 산출됐는지 사람 말로 적은 문장. 카탈로그 정의에서 오고 답변 프롬프트도 같은 문장을 쓴다 (QUR.WEB.002). */
  basis: string | null;
}

export interface WidgetResponse {
  id: string;
  dashboardId: string;
  template: string;
  title: string;
  spec: WidgetSpec;
  createdAt: string;
  updatedAt: string;
}

export interface DashboardPresetResponse {
  id: string;
  name: string;
  widgetCount: number;
  createdByName: string;
  createdAt: string;
}

export interface DashboardPresetSaveRequest {
  name: string;
  dashboardId: string;
}

export interface WidgetCreateRequest {
  spec: WidgetSpec;
  gridItem: GridItem;
}

export interface WidgetUpdateRequest {
  spec: WidgetSpec;
}

export interface WidgetPreviewRequest {
  spec: WidgetSpec;
}

export interface WidgetDataRequest {
  projectScopeOverride: string[] | null;
  periodOverride: WidgetFilter | null;
}

export interface WidgetGenerateRequest {
  prompt: string;
  template: WidgetTemplate | null;
  projectScope: string[];
  dashboardId: string | null;
}

export interface WidgetGenerationRejection {
  reason: string;
  unmatchedTerms: string[];
  suggestedAction: string | null;
  suggestedQuestion: string | null;
}

export interface WidgetGenerateResponse {
  status: 'GENERATED' | 'NOT_EXPRESSIBLE';
  spec: WidgetSpec | null;
  preview: WidgetDataResponse | null;
  rejection: WidgetGenerationRejection | null;
}

export interface DashboardCreateRequest {
  name: string;
  projectId: string | null;
}

export interface DashboardUpdateRequest {
  name: string;
}

export interface DashboardLayoutUpdateRequest {
  layout: DashboardLayout;
}

export interface DashboardSummaryResponse {
  id: string;
  name: string;
  projectId: string | null;
  projectName: string | null;
  isDefault: boolean;
  widgetCount: number;
  editable: boolean;
  updatedAt: string;
}

export interface DashboardDetailResponse {
  id: string;
  name: string;
  projectId: string | null;
  projectName: string | null;
  isDefault: boolean;
  editable: boolean;
  layout: DashboardLayout;
  widgets: WidgetResponse[];
  updatedAt: string;
}

export interface SemanticMeasureResponse {
  key: string;
  label: string;
  description: string | null;
  unit: string | null;
  allowedDimensions: string[];
  allowedFilters: string[];
  defaultTemplates: string[];
  status: string;
}

export interface SemanticDimensionResponse {
  key: string;
  label: string;
  description: string | null;
  valueType: string;
  enumValues: string[];
  status: string;
}

export interface SemanticFilterResponse {
  key: string;
  field: string;
  op: string;
  label: string;
  valueType: string;
  enumValues: string[];
  status: string;
}

export interface SemanticCatalogResponse {
  measures: SemanticMeasureResponse[];
  dimensions: SemanticDimensionResponse[];
  filters: SemanticFilterResponse[];
}

export interface AskRequest {
  question: string;
  projectScope: string[];
  /** 권장 질문을 눌렀을 때 그 키. 서버가 다시 검증하고 재분류하지 않는다 */
  hint?: string | null;
}

/** 이어 물을 질문 하나. 문장은 서버가 만들고 hint 는 누를 때 같이 보낸다 */
export interface SuggestionItem {
  question: string;
  hint: string;
}

export interface SseSuggestionsEvent {
  items: SuggestionItem[];
}

/** 지금 답변 모델. fixed 면 고정 응답(시험용)이라 실제 모델 답이 아니다 */
export interface AiRuntimeResponse {
  llmProvider: string;
  model: string | null;
  fixed: boolean;
  /** 실행 코드 이름표. 미리보기·배포를 띄울 때 넣는다 */
  codeVersion?: string | null;
}

export interface ConversationCreateRequest {
  title: string | null;
  projectScope: string[];
}

export interface ConversationUpdateRequest {
  title: string | null;
  pinned: boolean | null;
  projectScope: string[] | null;
}

export interface ConversationResponse {
  id: string;
  title: string;
  projectScope: string[];
  projectNames: string[];
  pinned: boolean;
  messageCount: number;
  lastMessageAt: string | null;
  createdAt: string;
}

export interface QueryRouting {
  type: RouteType;
  rewrittenQuery: string | null;
  measureKey: string | null;
  dimensions: string[];
  /** 모델이 고른 그림 형태. 서버가 데이터 모양으로 검증해 바꾸거나 버릴 수 있다. */
  viz: WidgetTemplate | null;
  listing?: string | null;
  /** 목록의 상태 조건. OPEN(처리 중) · CLOSED(완료) · ALL */
  listingStatus?: string | null;
  /** 판정을 라우팅 캐시에서 가져왔는가. 값은 그래도 매번 새로 뽑는다 */
  routeCached?: boolean;
  /** 일정 질문 묶음 키 (INTENT 일 때) */
  intent?: string | null;
}

/**
 * 답변에 끼워 넣는 그림 하나. 값은 시맨틱 레이어의 집계이거나 표준 모델의 행이고,
 * 모델은 무엇을 그릴지만 골랐다. slot 은 본문의 `[그림 N]` 표식 번호다.
 */
export interface SseInfographicEvent {
  slot: number;
  template: WidgetTemplate;
  title: string;
  data: WidgetDataResponse;
  /** 그림 아래 설명. 목록이면 "총 N건 중 앞 M건" */
  note: string | null;
}

export interface MessageSourceResponse {
  footnoteNo: number;
  docChunkId: string;
  sourceType: ChunkSourceType;
  sourceId: string;
  sourceLabel: string;
  projectId: string;
  projectName: string;
  snippet: string;
  externalUrl: string | null;
  documentUrl: string | null;
  pageNo: number | null;
  /** 원문 위치를 사람 말로(표제 경로 / 쪽 / 행). 서버 문장 그대로 보인다 (SWFR.RAG.006) */
  location: string | null;
}

export interface MessageResponse {
  id: string;
  conversationId: string;
  seq: number;
  role: MessageRole;
  content: string;
  routing: QueryRouting | null;
  sources: MessageSourceResponse[];
  feedback: MessageFeedback | null;
  createdAt: string;
  /** 생성 시점에 함께 보여준 그림들. 본문의 [그림 N] 자리에 들어간다. */
  infographics: SseInfographicEvent[];
  /** 답을 만드는 데 든 시간(ms). 스트리밍 중이거나 옛 메시지면 null */
  latencyMs: number | null;
  /** 답의 종류. STOP·PARTIAL·NO_DATA 등. 옛 메시지면 null */
  finishReason?: string | null;
  suggestions?: SuggestionItem[];
}

export interface MessageFeedbackRequest {
  feedback: MessageFeedback;
}

export interface SuggestedQuestionsResponse {
  questions: string[];
}

export interface SseStartEvent {
  conversationId: string;
  userMessageId: string;
  assistantMessageId: string;
  routing: QueryRouting | null;
  retrievedChunkCount: number;
}

export interface SseDeltaEvent {
  text: string;
}

export interface SseSourcesEvent {
  sources: MessageSourceResponse[];
}

export interface SseDoneEvent {
  assistantMessageId: string;
  finishReason: string;
  elapsedMs: number;
}

/** 색인된 본문 한 조각. 전문 열람은 이 조각을 순서대로 이어 붙여 보여 준다. */
export interface DocumentChunkResponse {
  index: number;
  content: string;
}

/** 문서 처리 작업 상태(GH-121). 접수됨 · 처리 중 · 완료 · 실패 */
export type DocumentProcessingState = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED';

export interface DocumentUploadResponse {
  id: string;
  projectId: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
  status: DocumentStatus;
  uploadedBy: string;
  uploadedAt: string;
  extractedCharCount: number | null;
  draftAvailable: boolean;
  workProductId: string | null;
  error: string | null;
  processingState: DocumentProcessingState;
  processingError: string | null;
}

/** 일별 스냅샷 한 줄. 그날 지표를 고정한 값이다. */
export interface ProgressSnapshotResponse {
  projectId: string;
  snapshotDate: string;
  level: string;
  representativePct: number | null;
  wbsActualPct: number | null;
  wbsPlannedPct: number | null;
  behindTaskCount: number;
  issueResolvedCount: number;
  issueTotalCount: number;
  requirementVerifiedCount: number;
  requirementTotalCount: number;
  riskClosedCount: number;
  riskTotalCount: number;
  workProductSubmittedCount: number;
  workProductApprovedCount: number;
  workProductTotalCount: number;
  createdAt: string;
}

/** 사업별 자동 수집 주기와 일별 스냅샷 시각. 서버 안 스케줄러가 읽는다. */
export interface ProjectScheduleResponse {
  projectId: string;
  syncIntervalMinutes: number;
  /** "HH:MM". 하루 한 번일 때 도는 시각 */
  syncTime: string;
  /** "HH:MM", 사업 시간대 */
  snapshotTime: string;
  /** 24 면 정한 시각에 하루 한 번. 작으면 그날 줄을 그 간격으로 다시 찍는다 */
  snapshotIntervalHours: number;
  snapshotOptions: { hours: number; label: string }[];
  timezone: string;
  options: { minutes: number; label: string }[];
  minIntervalMinutes: number;
  lastSnapshotDate: string | null;
  nextSnapshotAt: string;
  editable: boolean;
  updatedAt: string | null;
}

/** 활동 한 줄. 알림과 활동 탭이 같은 것을 본다. */
export interface ActivityEventResponse {
  id: string;
  projectId: string;
  projectName: string;
  occurredAt: string;
  kind: string;
  audience: 'CLIENT' | 'CONTRACTOR' | 'ALL';
  actorLabel: string;
  targetType: string | null;
  targetKey: string | null;
  summary: string;
  detail: Record<string, unknown>;
}

export interface NotificationsResponse {
  items: ActivityEventResponse[];
  unread: number;
  seenAt: string | null;
}

/** 서버 오류 기록 한 건. 최고관리자 화면용. */
export interface ErrorLogResponse {
  id: string;
  occurredAt: string;
  method: string;
  path: string;
  statusCode: number;
  code: string;
  message: string;
  exception: string | null;
  traceback: string | null;
  username: string | null;
  userName: string | null;
}

/** 자료 상세. 왼쪽 정보·설정, 오른쪽 추출 결과의 재료다. */
export interface DocumentDetailResponse {
  id: string;
  projectId: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
  status: DocumentStatus;
  error: string | null;
  uploadedBy: string;
  uploadedAt: string;
  pageCount: number | null;
  extractedCharCount: number | null;
  wbsId: string | null;
  wbsName: string | null;
  productType: string | null;
  proposedType: string | null;
  draftStatus: StructuringDraftStatus | null;
  workProductId: string | null;
  downloadUrl: string;
  originalUrl: string | null;
  processingState: DocumentProcessingState;
  processingError: string | null;
  /** 단계별 걸린 시간(초)·쪽수·청크 수. 처리 중에도 지금까지의 값이 온다 */
  processingSteps: Record<string, number | null> | null;
}

export interface DocumentUpdateRequest {
  wbsId?: string;
  productType?: string;
}

/** 추출 결과 원문. 파싱이 제대로 됐는지 사람이 눈으로 확인하는 용도다. */
export interface DocumentTextResponse {
  id: string;
  fileName: string;
  status: DocumentStatus;
  charCount: number;
  pageCount: number | null;
  text: string;
}

export interface DraftRequirement {
  index: number;
  code: string | null;
  title: string;
  body: string;
  priority: Priority;
}

export interface StructuringDraftResponse {
  documentId: string;
  status: StructuringDraftStatus;
  suggestedType: WorkProductType | null;
  rejectedTypeRaw: string | null;
  confidence: number;
  title: string | null;
  version: string | null;
  authoredDate: string | null;
  requirements: DraftRequirement[];
  createdAt: string;
}

export interface StructuringConfirmRequest {
  type: WorkProductType;
  title: string;
  version: string;
  authoredDate: string | null;
  requirements: DraftRequirement[];
  workProductStatus: WorkProductStatus;
}

export interface StructuringConfirmResponse {
  workProductId: string;
  createdRequirementIds: string[];
  indexedChunkCount: number;
}

// ---------------------------------------------------------------- 일정 (WBS)

/** 일정 화면의 원천. 화면은 이 값으로 설명문과 고지문을 바꾼다. */
export type WbsSource = 'WBS_FILE' | 'REDMINE' | 'NONE';

export interface WbsItemResponse {
  wbsId: string;
  name: string;
  /** 들여쓰기 깊이. 0 이 최상위. */
  level: number;
  owner: string;
  deliverable: string | null;
  startDate: string | null;
  endDate: string | null;
  /** 상위 항목·Redmine 이슈는 없다. */
  weight: number | null;
  /** 0~100 */
  progress: number;
  /** 기준일의 계획 진척. 0~100 */
  planned: number;
  externalUrl: string | null;
  /** 산출물 판정(ARC-016). 묶음·산출물 열 없음은 NONE */
  deliverableStatus?: DeliverableStatus;
  deliverableRule?: 'REPO_PATH' | 'FILE_NAME' | 'PRODUCT_TYPE' | null;
  deliverableRef?: string | null;
  deliverableUrl?: string | null;
}

export type DeliverableStatus = 'NONE' | 'SUBMITTED' | 'MISSING' | 'OVERDUE';

export interface DeliverableSummary {
  submitted: number;
  missing: number;
  overdue: number;
  none: number;
}

/** 산출물 화면 한 줄. WBS 말단 작업이 정한 산출물과 판정, 붙은 문서, 29110 태그 (ARC-016). */
export interface WbsDeliverableDocument {
  id: string;
  fileName: string;
  status: DocumentStatus;
  uploadedAt: string;
  proposedType: string | null;
  confirmed: boolean;
}

export interface WbsDeliverableItem {
  wbsId: string;
  name: string;
  deliverable: string | null;
  endDate: string | null;
  status: DeliverableStatus;
  rule: 'LINKED_DOC' | 'REPO_PATH' | 'FILE_NAME' | 'PRODUCT_TYPE' | null;
  ref: string | null;
  url: string | null;
  productType: string | null;
  documents: WbsDeliverableDocument[];
}

export interface WbsDeliverablesResponse {
  baseDate: string;
  items: WbsDeliverableItem[];
  summary: DeliverableSummary;
}

export interface WbsScheduleResponse {
  source: WbsSource;
  sourceLabel: string;
  sourceUrl: string | null;
  baseDate: string;
  planVersion: string | null;
  planUpdatedAt: string | null;
  items: WbsItemResponse[];
  warnings: string[];
  deliverables?: DeliverableSummary;
  /** 원천이 없을 때만. 진척률 산정의 핵심 입력이 빠졌음을 그대로 보인다. */
  notice: string | null;
}

// --- AI 모델 설정 (ARC-011) ----------------------------------------------------

export interface LlmModelResponse {
  name: string;
  baseUrl: string;
  /** 서버가 안 알려주면 0 */
  contextLength: number;
  supportsTools: boolean;
  parameterSize: string | null;
  quantization: string | null;
  /** 실측 생성 속도. 미측정이면 null */
  tokPerSec: number | null;
  measuredAt: string | null;
  /** 비우면 모델 기본값에 맡긴다 */
  numCtx: number | null;
  numPredict: number;
  fetchedAt: string;
  /** 서버가 알려준 용도. 안 알려주면 null */
  capabilities: string[] | null;
  /** ANSWER 답변용 · EMBEDDING 검색 전용 · UNKNOWN 확인 필요 (ARC-022) */
  purpose: LlmModelPurpose;
  /** 마지막 짧은 생성 확인 성공 시각 */
  verifiedAt: string | null;
}

export type LlmModelPurpose = 'ANSWER' | 'EMBEDDING' | 'UNKNOWN';

export interface LlmModelListResponse {
  baseUrl: string;
  models: LlmModelResponse[];
  /** 조회 실패는 예외가 아니라 상태 문구다 */
  error: string | null;
}

export interface LlmSettingResponse {
  baseUrl: string;
  model: string;
  provider: string;
  /** 한 요청이 쓸 수 있는 초. 0 이면 미설정 */
  requestTimeoutSeconds: number;
  updatedAt: string | null;
  models: LlmModelResponse[];
  /** 지금 적용 중인 값의 출처. DB 저장값 또는 환경변수 기본값 */
  source: 'DB' | 'ENV';
  /** 이 모델이 쓰이는 곳 */
  usedFor: string[];
}

/** 검색 모델(임베딩). 환경변수로 정하고 화면에서 바꾸지 않는다 (ARC-022) */
export interface EmbeddingStatusResponse {
  provider: string;
  baseUrl: string;
  model: string;
  dimension: number;
  columnDimension: number | null;
  source: 'ENV';
  /** 서버 목록에 있는가. 확인 못 하면 null */
  serverHasModel: boolean | null;
  serverCapabilities: string[] | null;
  indexModels: { model: string; chunks: number }[];
  /** 색인이 모두 지금 모델로 만들어졌는가 */
  consistent: boolean;
  /** 맞지 않을 때 이유. 문서 검색과 색인이 멈춰 있다 */
  message: string | null;
  changeBlockedReason: string;
}

export interface LlmSettingUpdateRequest {
  baseUrl: string;
  model: string;
  numCtx: number | null;
  numPredict: number;
}

export interface LlmMeasureResponse {
  model: string;
  tokPerSec: number;
  evalCount: number;
  evalDurationSeconds: number;
  measuredAt: string;
}

// --- 인포 템플릿 카탈로그 (ARC-012) --------------------------------------------

export type TemplateTimeAxis = 'REQUIRED' | 'OPTIONAL' | 'NONE';

export interface WidgetTemplateExample {
  measure: string;
  dimensions: string[];
  title: string;
}

export interface WidgetTemplateResponse {
  key: WidgetTemplate;
  label: string;
  family: string;
  purpose: string;
  screen: string;
  when: string;
  measureTypes: string[];
  dimsMin: number;
  dimsMax: number;
  timeAxis: TemplateTimeAxis;
  /** 읽을 수 있는 범주 수 상한. 표 성격이면 null */
  categoryMax: number | null;
  usesTotal: boolean;
  usesTarget: boolean;
  usesPrevious: boolean;
  options: string[];
  rowCap: number;
  chat: boolean;
  note: string;
  example: WidgetTemplateExample;
  /** "표시할 내용" 에 이렇게 적으라는 예시 문장 */
  prompts: string[];
  /** 쇼케이스용 예시 값. 계약에서 만든 결정적 값이라 사업이 없어도 그려진다 */
  sample: WidgetDataResponse;
}

export interface WidgetTemplateListResponse {
  templates: WidgetTemplateResponse[];
}

// --- 요구사항 기준선 (GH-139, ARC-028) ---

export type BaselineStatus = 'DRAFT' | 'SUBMITTED' | 'CONFIRMED';
export type BaselineState = 'NONE' | BaselineStatus;
/** DUPLICATE_CODE · INVALID_CODE · MISSING_TITLE 는 제출 전에 고친다. UNTRACEABLE_CODE 는 경고 */
export type BaselineProblem =
  'DUPLICATE_CODE' | 'INVALID_CODE' | 'MISSING_TITLE' | 'UNTRACEABLE_CODE';
export type BaselineMatch = 'NEW' | 'SAME' | 'CHANGED';

export interface BaselineExisting {
  requirementId: string;
  code: string;
  title: string;
  priority: Priority;
  /** 기존 요구사항이 어디서 왔는지. 연결 이름, "문서", "수기" */
  source: string;
}

export interface BaselineItem {
  id: string;
  seq: number;
  code: string | null;
  title: string;
  body: string;
  priority: Priority;
  /** 명세서 안 위치. 손으로 더한 항목은 없다 */
  location: string | null;
  origin: 'EXTRACTED' | 'MANUAL';
  edited: boolean;
  problems: BaselineProblem[];
  /** 확정 전에는 지금 기준 미리보기다 */
  match: BaselineMatch | null;
  existing: BaselineExisting | null;
  requirementId: string | null;
  specApplied: boolean;
}

/** 명세서 절 제목의 상위 요구사항. 요구사항 목록에는 들지 않는다. */
export interface BaselineParent {
  code: string;
  title: string;
  location: string | null;
  children: string[];
}

export interface BaselineResponse {
  id: string;
  version: number;
  status: BaselineStatus;
  documentId: string | null;
  sourceFilename: string;
  sourceDocVersion: string | null;
  createdBy: string | null;
  createdAt: string;
  submittedBy: string | null;
  submittedAt: string | null;
  returnedReason: string | null;
  confirmedBy: string | null;
  confirmedByRole: string | null;
  confirmedAt: string | null;
  items: BaselineItem[];
  blockingCount: number;
  extractionEmpty: boolean;
  counts: Record<BaselineMatch, number>;
  /** 기존 요구사항 중 명세서에 없는 코드. 지우지 않고 기준선 밖으로 둔다 */
  missing: BaselineExisting[];
  parents: BaselineParent[];
}

export interface BaselineStateResponse {
  state: BaselineState;
  confirmed: BaselineResponse | null;
  /** 발주기관에게 작성 중(DRAFT) 목록은 오지 않는다 */
  working: BaselineResponse | null;
  workingStatus: BaselineStatus | null;
  requirementCount: number;
  outsideBaselineCount: number;
  unresolvedCodeCount: number;
}

export interface UnresolvedRefResponse {
  code: string;
  sourceType: string;
  sourceId: string;
  sourceLabel: string;
  evidenceText: string | null;
  evidenceUrl: string | null;
  /** 가리킨 코드가 기준선의 상위 요구사항이면 그 명칭. 없는 ID 가 아니다 */
  parentTitle?: string | null;
}
