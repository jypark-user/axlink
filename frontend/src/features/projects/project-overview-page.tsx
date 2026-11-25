import { useState, type ReactNode } from 'react';
import { Pencil } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tile } from '@/components/ui/page';
import { Window } from '@/components/ui/window';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { AssignmentsPage } from '@/features/assignments/assignments-page';
import { useAuth } from '@/features/auth/auth-context';
import { useToast } from '@/components/common/toaster';
import { ProjectEditDialog } from '@/features/projects/project-edit-dialog';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime, formatPeriod } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import type { ProjectDetailResponse } from '@/types/api';

/**
 * 사업 관리(11-20 사용자 지시). 기본 정보와 용역사만 둔다. 예전의 사업 세부 내용(관련자료 업로드·원문)과
 * 요구사항 표는 뺐다. 자료는 자료 화면, 요구사항은 요구사항 화면에서 본다.
 */
export function ProjectOverviewPage(): ReactNode {
  const { project, replaceProject } = useProjectContext();
  const { me } = useAuth();
  const [editOpen, setEditOpen] = useState(false);
  const { toast } = useToast();
  const canEdit = me?.role === 'CLIENT';
  const closed = project.status === 'CLOSED';

  // 종료는 보관이다. 데이터는 그대로 두고 예약 수집·스냅샷만 멈춘다. 되돌리지 않으므로 한 번 묻는다.
  const closeProject = async () => {
    const ok = window.confirm(
      `「${project.name}」을 종료 처리할까요? 데이터는 그대로 남고 예약 수집과 일별 스냅샷이 멈춥니다. 되돌릴 수 없습니다.`,
    );
    if (!ok) return;
    try {
      const updated = await api.patch<ProjectDetailResponse>(`/projects/${project.id}`, {
        status: 'CLOSED',
      });
      replaceProject(updated);
      toast({ title: '사업을 종료 처리했습니다.', variant: 'success' });
    } catch (err) {
      toast({
        title: '종료 처리하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <>
      <PageHeader guide="project-setup#overview" title="사업 관리" />
      <div className="@container">
        <div className="grid grid-cols-1 items-start gap-3 @3xl:grid-cols-12">
          <Tile span={12}>
            <Window
              title="기본 정보"
              action={
                canEdit ? (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                      <Pencil className="size-4" />
                      수정
                    </Button>
                    {!closed && (
                      <Button variant="outline" size="sm" onClick={() => void closeProject()}>
                        종료 처리
                      </Button>
                    )}
                  </div>
                ) : null
              }
            >
              <dl className="grid grid-cols-1 gap-x-6 gap-y-3 @2xl:grid-cols-2">
                <Row term="사업명" desc={project.name} />
                <Row
                  term="상태"
                  desc={
                    <Badge variant={badgeVariantFor(project.status)}>{label(project.status)}</Badge>
                  }
                />
                <Row term="사업 기간" desc={formatPeriod(project.startDate, project.endDate)} />
                <Row term="발주사" desc={project.clientOrgName} />
                <Row term="용역사" desc={project.contractorName} />
                <Row term="현재 SI 단계" desc={label(project.currentSiPhase)} />
                <Row term="최근 수정" desc={formatDateTime(project.updatedAt)} />
              </dl>

              <p className="text-foreground text-sm mt-5 whitespace-pre-line">
                {project.description || '설명이 없습니다.'}
              </p>
            </Window>
          </Tile>

          {canEdit && (
            <Tile span={12}>
              <Window title="용역사">
                <AssignmentsPage />
              </Window>
            </Tile>
          )}
        </div>

        {canEdit && (
          <ProjectEditDialog
            project={project}
            open={editOpen}
            onOpenChange={setEditOpen}
            onSaved={replaceProject}
          />
        )}
      </div>
    </>
  );
}

function Row({ term, desc }: { term: string; desc: ReactNode }): ReactNode {
  return (
    <div className="flex min-w-0 items-baseline gap-3">
      <dt className="text-muted-foreground text-sm w-24 shrink-0">{term}</dt>
      <dd className="text-foreground text-sm min-w-0 truncate">{desc}</dd>
    </div>
  );
}
