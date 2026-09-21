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
  | 'CORRECTION_ACTION';
export type TraceLinkKind = 'DESIGNS' | 'IMPLEMENTS' | 'TESTS' | 'DELIVERS';
export type TraceLinkOrigin = 'AUTO' | 'MANUAL';
export type TraceLinkStatus = 'ACTIVE' | 'BROKEN';
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
export type RouteType = 'DOCUMENT' | 'AGGREGATE' | 'MIXED';
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
  credentialMasked: string;
  status: ConnectionStatus;
  lastSyncedAt: string | null;
  lastSyncStatus: SyncJobStatus | null;
  lastSyncError: string | null;
  ingestedCount: number;
  mappingRuleCount: number;
  createdAt: string;
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
}

export interface TraceabilityRowResponse {
  requirementId: string;
  requirementCode: string;
  requirementTitle: string;
  requirementStatus: RequirementStatus;
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
}

export interface RequirementDetailResponse extends RequirementResponse {
  body: string;
  traceLinks: TraceLinkResponse[];
  history: EntityHistoryResponse[];
}

export interface IssueResponse {
  id: string;
  projectId: string;
  key: string;
  title: string;
  status: IssueStatus;
  severity: IssueSeverity | null;
  assignee: string | null;
  resolvedAt: string | null;
  source: SourceRef;
  updatedAt: string;
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
export type ReviewEventKind = 'REQUESTED' | 'REPORTED' | 'CONFIRMED' | 'REREQUESTED';

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
}

export interface ReviewRequestDetailResponse extends ReviewRequestResponse {
  snapshot: Record<string, unknown>;
  currentState: Record<string, unknown>;
  changes: ReviewStateChange[];
  events: ReviewRequestEventResponse[];
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
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
  requirements: DraftRequirement[];
  createdAt: string;
}

export interface StructuringConfirmRequest {
  type: WorkProductType;
  title: string;
  version: string;
  authoredDate: string | null;
  pmActivity: PmActivity | null;
  siActivity: SiPhase | null;
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
}

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
  /** 쇼케이스용 예시 값. 계약에서 만든 결정적 값이라 사업이 없어도 그려진다 */
  sample: WidgetDataResponse;
}

export interface WidgetTemplateListResponse {
  templates: WidgetTemplateResponse[];
}
