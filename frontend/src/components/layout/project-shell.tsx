import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Navigate, Outlet, useParams } from 'react-router-dom';
import { request } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { Skeleton } from '@/components/ui/skeleton';
import type { ProjectDetailResponse } from '@/types/api';

interface ProjectContextValue {
  project: ProjectDetailResponse;
  /** 사업 정보를 고친 뒤 화면을 바로 맞춘다 — 다시 불러올 것 없이 응답을 그대로 쓴다. */
  replaceProject: (next: ProjectDetailResponse) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

/** 프로젝트 밖(전역 화면)에서도 부를 수 있는 조회. 없으면 null. */
export const useOptionalProject = (): ProjectDetailResponse | null =>
  useContext(ProjectContext)?.project ?? null;

export const useProjectContext = (): ProjectContextValue => {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProjectContext must be used within ProjectShell');
  return ctx;
};

export function ProjectShell(): ReactNode {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setProject(null);
    setError(null);
    request<ProjectDetailResponse>(`/projects/${projectId}`)
      .then((p) => {
        if (!cancelled) setProject(p);
      })
      .catch((e) => {
        if (cancelled) return;
        if (isApiError(e) && (e.status === 403 || e.code === 'PROJECT_ACCESS_DENIED')) {
          setError('FORBIDDEN');
        } else if (isApiError(e) && e.status === 404) {
          setError('NOT_FOUND');
        } else {
          setError('ERROR');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (error === 'FORBIDDEN') return <Navigate to="/403" replace />;
  if (error === 'NOT_FOUND') return <Navigate to="/404" replace />;

  return (
    <>
      {!project ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-10 w-1/2" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <ProjectContext.Provider value={{ project, replaceProject: setProject }}>
          <Outlet />
        </ProjectContext.Provider>
      )}
    </>
  );
}
