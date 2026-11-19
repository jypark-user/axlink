import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthLayout } from '@/components/layout/auth-layout';
import { AppShell } from '@/components/layout/app-shell';
import { ProjectShell } from '@/components/layout/project-shell';
import { RequireAuth, RequireProject, RequireRole } from '@/features/auth/guards';
import { ForbiddenPage } from '@/components/common/forbidden-page';
import { NotFoundPage } from '@/components/common/not-found-page';
import { DevWidgetSizes } from '@/features/dashboard/dev-widget-sizes';
import { Skeleton } from '@/components/ui/skeleton';
import type { Role } from '@/types/api';

const LoginPage = lazy(() =>
  import('@/features/auth/login-page').then((m) => ({ default: m.LoginPage })),
);
const InviteAcceptPage = lazy(() =>
  import('@/features/auth/invite-accept-page').then((m) => ({ default: m.InviteAcceptPage })),
);
const GuidePage = lazy(() =>
  import('@/features/help/guide-page').then((m) => ({ default: m.GuidePage })),
);
const GuidePrintPage = lazy(() =>
  import('@/features/help/guide-print-page').then((m) => ({ default: m.GuidePrintPage })),
);
const ProjectListPage = lazy(() =>
  import('@/features/projects/project-list-page').then((m) => ({ default: m.ProjectListPage })),
);
const ProjectOverviewPage = lazy(() =>
  import('@/features/projects/project-overview-page').then((m) => ({
    default: m.ProjectOverviewPage,
  })),
);
const DashboardPage = lazy(() =>
  import('@/features/dashboard/dashboard-page').then((m) => ({ default: m.DashboardPage })),
);
const ConnectionsPage = lazy(() =>
  import('@/features/connections/connections-page').then((m) => ({ default: m.ConnectionsPage })),
);
const AssignmentsPage = lazy(() =>
  import('@/features/assignments/assignments-page').then((m) => ({ default: m.AssignmentsPage })),
);
const CollectionPage = lazy(() =>
  import('@/features/collection/collection-page').then((m) => ({ default: m.CollectionPage })),
);
const TemplatesPage = lazy(() =>
  import('@/features/templates/templates-page').then((m) => ({ default: m.TemplatesPage })),
);
const ErrorLogPage = lazy(() =>
  import('@/features/admin/error-log-page').then((m) => ({ default: m.ErrorLogPage })),
);
const AccountsPage = lazy(() =>
  import('@/features/admin/accounts-page').then((m) => ({ default: m.AccountsPage })),
);
const DocumentsPage = lazy(() =>
  import('@/features/documents/documents-page').then((m) => ({ default: m.DocumentsPage })),
);
const DocumentDetailPage = lazy(() =>
  import('@/features/documents/document-detail-page').then((m) => ({
    default: m.DocumentDetailPage,
  })),
);
const BaselinePage = lazy(() =>
  import('@/features/requirement-baseline/baseline-page').then((m) => ({
    default: m.BaselinePage,
  })),
);
const DeliverablesPage = lazy(() =>
  import('@/features/deliverables/deliverables-page').then((m) => ({
    default: m.DeliverablesPage,
  })),
);
const TraceabilityPage = lazy(() =>
  import('@/features/traceability/traceability-page').then((m) => ({
    default: m.TraceabilityPage,
  })),
);
const IssuesPage = lazy(() =>
  import('@/features/issues/issues-page').then((m) => ({ default: m.IssuesPage })),
);
const SchedulePage = lazy(() =>
  import('@/features/schedule/schedule-page').then((m) => ({ default: m.SchedulePage })),
);
const SnapshotsPage = lazy(() =>
  import('@/features/snapshots/snapshots-page').then((m) => ({ default: m.SnapshotsPage })),
);
const ReviewRequestsPage = lazy(() =>
  import('@/features/review-requests/review-requests-page').then((m) => ({
    default: m.ReviewRequestsPage,
  })),
);
const AskPage = lazy(() =>
  import('@/features/ax-query/ask-page').then((m) => ({ default: m.AskPage })),
);

/** 용역사(CONTRACTOR)는 사업 정보·연동·동기화 이력만 본다. 나머지 화면은 이 목록으로 막는다. */
const EXCEPT_CONTRACTOR: Role[] = ['SUPER_ADMIN', 'CLIENT'];

function PageFallback(): ReactNode {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <Skeleton className="h-8 w-48" />
    </div>
  );
}

function SuspenseShell({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export function AppRoutes(): ReactNode {
  return (
    <Routes>
      {/* 개발용 자 — 위젯 최소 크기를 눈으로 재는 화면. 표본 값이라 로그인이 필요 없다. */}
      {import.meta.env.DEV && <Route path="/dev/widget-sizes" element={<DevWidgetSizes />} />}
      {/* 개발용 자 — 편집 중 칸 바탕이 실제 위젯 자리와 맞는지 잰다. */}

      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite/accept" element={<InviteAcceptPage />} />
      </Route>

      {/* 설명서 인쇄(PDF) — 메뉴 없이 본문만 이어 그려야 쪽이 제대로 나뉜다. 화면 틀 밖에 둔다 */}
      <Route
        path="/guide/print"
        element={
          <RequireAuth>
            <SuspenseShell>
              <GuidePrintPage />
            </SuspenseShell>
          </RequireAuth>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route
          path="/projects"
          element={
            <SuspenseShell>
              <ProjectListPage />
            </SuspenseShell>
          }
        />
        {/* 사용 설명서 — 역할과 사업에 상관없이 본다. 각 화면이 /guide/<문서>#<절> 로 바로 연다 */}
        <Route
          path="/guide/:slug?"
          element={
            <SuspenseShell>
              <GuidePage />
            </SuspenseShell>
          }
        />
        {/* 인포 템플릿 카탈로그 — 플랫폼 관리자만. 사업과 무관한 정의라 전역에 둔다 (ARC-012) */}
        <Route element={<RequireRole allow={['SUPER_ADMIN']} />}>
          <Route
            path="/templates"
            element={
              <SuspenseShell>
                <TemplatesPage />
              </SuspenseShell>
            }
          />
          <Route
            path="/admin/errors"
            element={
              <SuspenseShell>
                <ErrorLogPage />
              </SuspenseShell>
            }
          />
          <Route
            path="/admin/accounts"
            element={
              <SuspenseShell>
                <AccountsPage />
              </SuspenseShell>
            }
          />
        </Route>
        <Route element={<RequireRole allow={EXCEPT_CONTRACTOR} />}>
          {/* 한 라우트로 둔다 — 대화를 새로 열 때 화면이 다시 뜨면 쓰던 것이 다 날아간다. */}
          <Route
            path="/ask/:conversationId?"
            element={
              <SuspenseShell>
                <AskPage />
              </SuspenseShell>
            }
          />
        </Route>
        <Route
          path="/dashboards/:dashboardId"
          element={
            <RequireRole allow={['CLIENT']}>
              <SuspenseShell>
                <DashboardPage />
              </SuspenseShell>
            </RequireRole>
          }
        />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="/404" element={<NotFoundPage />} />

        <Route
          path="/p/:projectId"
          element={
            <RequireProject>
              <ProjectShell />
            </RequireProject>
          }
        >
          {/* 용역사도 볼 수 있는 화면 — 사업 정보 · 연동 · 동기화 이력 */}
          <Route
            index
            element={
              <SuspenseShell>
                <ProjectOverviewPage />
              </SuspenseShell>
            }
          />
          <Route
            path="connections"
            element={
              <SuspenseShell>
                <ConnectionsPage />
              </SuspenseShell>
            }
          />
          <Route
            path="collection"
            element={
              <SuspenseShell>
                <CollectionPage />
              </SuspenseShell>
            }
          />
          {/* 확인 요청은 양쪽이 다 본다. 발주기관이 요청하고 용역사가 보고한다 */}
          <Route
            path="reviews"
            element={
              <SuspenseShell>
                <ReviewRequestsPage />
              </SuspenseShell>
            }
          />

          {/* 용역사도 본다. 산출물 문서를 올리는 쪽이 용역사고, 올린 것이 WBS 산출물 판정과
              22종 항목의 재료가 된다(ARC-016). 쓰기 권한은 서버가 사업 배정으로 가른다. */}
          <Route
            path="documents"
            element={
              <SuspenseShell>
                <DocumentsPage />
              </SuspenseShell>
            }
          />
          <Route
            path="documents/:documentId"
            element={
              <SuspenseShell>
                <DocumentDetailPage />
              </SuspenseShell>
            }
          />
          <Route
            path="deliverables"
            element={
              <SuspenseShell>
                <DeliverablesPage />
              </SuspenseShell>
            }
          />
          <Route
            path="dashboard"
            element={
              <SuspenseShell>
                <DashboardPage />
              </SuspenseShell>
            }
          />
          <Route
            path="traceability"
            element={
              <SuspenseShell>
                <TraceabilityPage />
              </SuspenseShell>
            }
          />
          <Route
            path="requirement-baseline"
            element={
              <SuspenseShell>
                <BaselinePage />
              </SuspenseShell>
            }
          />
          <Route
            path="schedule"
            element={
              <SuspenseShell>
                <SchedulePage />
              </SuspenseShell>
            }
          />
          <Route
            path="snapshots"
            element={
              <SuspenseShell>
                <SnapshotsPage />
              </SuspenseShell>
            }
          />
          <Route
            path="issues"
            element={
              <SuspenseShell>
                <IssuesPage />
              </SuspenseShell>
            }
          />
          <Route element={<RequireRole allow={EXCEPT_CONTRACTOR} />}>
            <Route
              path="ask/:conversationId?"
              element={
                <SuspenseShell>
                  <AskPage />
                </SuspenseShell>
              }
            />
          </Route>

          <Route element={<RequireRole allow={['CLIENT']} />}>
            <Route
              path="assignments"
              element={
                <SuspenseShell>
                  <AssignmentsPage />
                </SuspenseShell>
              }
            />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
