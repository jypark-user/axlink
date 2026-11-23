import { type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { useAuth } from '@/features/auth/auth-context';
import { ProjectForm, type ProjectFormValues } from '@/features/projects/project-form';
import { matchContractor, useContractorUsers } from '@/features/projects/contractor-picker';
import type { ProjectDetailResponse } from '@/types/api';

/**
 * 사업 등록. 여기서는 기본 정보만 받는다 —
 * 제안요청서 같은 문서는 사업을 만든 뒤 자료 화면에서 올린다.
 */
export function ProjectCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): ReactNode {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { refreshMe } = useAuth();
  const contractors = useContractorUsers();

  const users = contractors.data?.content ?? [];

  const submit = async (values: ProjectFormValues) => {
    const created = await api.post<ProjectDetailResponse>('/projects', values);

    // 사업은 이미 만들어졌다 — 뒤따르는 할당이 실패해도 등록을 되돌리지 않고 알리기만 한다.
    const match = matchContractor(values.contractorName, users);
    if (values.contractorName.trim() && !match) {
      toast({
        title: '사업은 등록했지만 용역사 계정을 찾지 못했습니다.',
        description: `'${values.contractorName.trim()}' 로 등록된 계정이 없습니다 · 계정이 만들어진 뒤 사업 관리 화면에서 할당하십시오.`,
        variant: 'error',
      });
    } else if (match) {
      try {
        await api.post(`/projects/${created.id}/assignments`, match);
      } catch (e) {
        toast({
          title: '사업은 등록했지만 용역사 할당에 실패했습니다.',
          description: `${isApiError(e) ? e.message : '할당에 실패했습니다.'} · 사업 관리 화면에서 다시 할당하십시오.`,
          variant: 'error',
        });
      }
    }

    // 새 사업이 내 접근 목록에 들어오도록 세션 정보를 다시 읽는다.
    await refreshMe();

    onOpenChange(false);
    void navigate(`/p/${created.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="px-6 pt-5 pb-4">
          <DialogTitle className="text-lg font-semibold tracking-tight">사업 등록</DialogTitle>
          <DialogDescription>
            사업 기본 정보를 입력합니다. 제안요청서 같은 문서는 등록한 뒤 자료 화면에서 올립니다.
          </DialogDescription>
        </DialogHeader>

        <div className="border-border/60 min-h-0 flex-1 overflow-y-auto border-t px-6 py-5">
          <ProjectForm
            submitLabel="등록"
            requireDeletePassword
            onCancel={() => onOpenChange(false)}
            onSubmit={submit}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
