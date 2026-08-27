import { type ReactNode } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { ProjectForm, type ProjectFormValues } from '@/features/projects/project-form';
import type { ProjectDetailResponse } from '@/types/api';

/** 사업 기본 정보 고치기. 등록 때와 같은 칸을 쓰고, 저장하면 응답으로 화면을 맞춘다. */
export function ProjectEditDialog({
  project,
  open,
  onOpenChange,
  onSaved,
}: {
  project: ProjectDetailResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (next: ProjectDetailResponse) => void;
}): ReactNode {
  const { toast } = useToast();

  const submit = async (values: ProjectFormValues) => {
    const updated = await api.patch<ProjectDetailResponse>(`/projects/${project.id}`, {
      ...values,
      currentSiPhase: null,
    });
    onSaved(updated);
    onOpenChange(false);
    toast({ title: '사업 정보를 고쳤습니다.', variant: 'success' });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="px-6 pt-5 pb-4">
          <DialogTitle className="text-lg font-semibold tracking-tight">사업 정보 수정</DialogTitle>
          <DialogDescription>등록할 때 입력한 기본 정보를 고칩니다.</DialogDescription>
        </DialogHeader>

        <div className="border-border/60 min-h-0 flex-1 overflow-y-auto border-t px-6 py-5">
          <ProjectForm
            initial={{
              name: project.name,
              startDate: project.startDate,
              endDate: project.endDate,
              description: project.description,
              contractorName: project.contractorName ?? '',
              deletePassword: '', // 수정에서는 쓰지 않는다 — 삭제 비밀번호는 등록에서만 정한다.
            }}
            submitLabel="저장"
            onCancel={() => onOpenChange(false)}
            onSubmit={submit}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
