import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthLayout } from '@/components/layout/auth-layout';
import { AppShell } from '@/components/layout/app-shell';
import { ProjectShell } from '@/components/layout/project-shell';
import { RequireAuth, RequireProject, RequireRole } from '@/features/auth/guards';
import { ForbiddenPage } from '@/components/common/forbidden-page';
import { NotFoundPage } from '@/components/common/not-found-page';
import { ComingSoon } from '@/components/common/coming-soon';
import { DevWidgetSizes } from '@/features/dashboard/dev-widget-sizes';
import { Skeleton } from '@/components/ui/skeleton';
import type { Role } from '@/types/api';

const LoginPage = lazy(() =>
  import('@/features/auth/login-page').then((m) => ({ default: m.LoginPage })),
);
const InviteAcceptPage = lazy(() =>
  import('@/features/auth/invite-accept-page').then((m) => ({ default: m.InviteAcceptPage })),
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
const DocumentsPage = lazy(() =>
  import('@/features/documents/documents-page').then((m) => ({ default: m.DocumentsPage })),
);
const StructuringDraftPage = lazy(() =>
  import('@/features/documents/structuring-draft-page').then((m) => ({
    default: m.StructuringDraftPage,
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
const ChangesPage = lazy(() =>
  import('@/features/changes/changes-page').then((m) => ({ default: m.ChangesPage })),
);
const AskPage = lazy(() =>
  import('@/features/ax-query/ask-page').then((m) => ({ default: m.AskPage })),
);
const OrganizationsPage = lazy(() =>
  import('@/features/admin/organizations-page').then((m) => ({ default: m.OrganizationsPage })),
);
const ContractorsPage = lazy(() =>
  import('@/features/admin/contractors-page').then((m) => ({ default: m.ContractorsPage })),
);
const AuditPage = lazy(() =>
  import('@/features/admin/audit-page').then((m) => ({ default: m.AuditPage })),
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
        <Route
          path="/admin/organizations"
          element={
            <RequireRole allow={['SUPER_ADMIN', 'CLIENT']}>
              <SuspenseShell>
                <OrganizationsPage />
              </SuspenseShell>
            </RequireRole>
          }
        />
        <Route
          path="/admin/contractors"
          element={
            <RequireRole allow={['SUPER_ADMIN']}>
              <SuspenseShell>
                <ContractorsPage />
              </SuspenseShell>
            </RequireRole>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <RequireRole allow={['SUPER_ADMIN', 'CLIENT']}>
              <SuspenseShell>
                <AuditPage />
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

          <Route element={<RequireRole allow={EXCEPT_CONTRACTOR} />}>
            <Route
              path="dashboard"
              element={
                <SuspenseShell>
                  <DashboardPage />
                </SuspenseShell>
              }
            />
            <Route
              path="documents"
              element={
                <SuspenseShell>
                  <DocumentsPage />
                </SuspenseShell>
              }
            />
            <Route
              path="documents/:documentId/draft"
              element={
                <SuspenseShell>
                  <StructuringDraftPage />
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
              path="traceability"
              element={
                <SuspenseShell>
                  <TraceabilityPage />
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
              path="issues"
              element={
                <SuspenseShell>
                  <IssuesPage />
                </SuspenseShell>
              }
            />
            <Route
              path="changes"
              element={
                <SuspenseShell>
                  <ChangesPage tab="CR" />
                </SuspenseShell>
              }
            />
            <Route
              path="corrections"
              element={
                <SuspenseShell>
                  <ChangesPage tab="CA" />
                </SuspenseShell>
              }
            />
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
            <Route path="acceptance" element={<ComingSoon title="검수" />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
