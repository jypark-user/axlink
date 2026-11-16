import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { label } from '@/lib/labels';
import type {
  RequirementDetailResponse,
  RequirementStatus,
  TraceabilityRowResponse,
} from '@/types/api';

const STATUSES: RequirementStatus[] = [
  'DEFINED',
  'DESIGNED',
  'IMPLEMENTED',
  'VERIFIED',
  'ACCEPTED',
  'REJECTED',
];

/**
 * 요구사항 상태 지정 창(ARC-025). 기본은 근거대로 움직이고, 발주기관은 사유를 남기고 어느
 * 상태로든 지정한다. 지정이 있으면 근거대로 되돌릴 수도 있다. 수집이 다시 돌아도 지정은 남는다.
 */
export function StatusDecisionDialog({
  projectId,
  row,
  onOpenChange,
  onSaved,
}: {
  projectId: string;
  row: TraceabilityRowResponse | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}): ReactNode {
  if (!row) return null;
  // 요구사항이 바뀌면 key 로 새 폼을 만든다. 고르던 상태·사유가 다른 요구사항으로 넘어가지 않는다
  return (
    <DecisionForm
      key={row.requirementId}
      projectId={projectId}
      row={row}
      onOpenChange={onOpenChange}
      onSaved={onSaved}
    />
  );
}

function DecisionForm({
  projectId,
  row,
  onOpenChange,
  onSaved,
}: {
  projectId: string;
  row: TraceabilityRowResponse;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [status, setStatus] = useState<RequirementStatus>(row.requirementStatus);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState<'decide' | 'revert' | null>(null);

  const decision = row.requirementDecision;
  const evidence = row.requirementEvidenceStatus ?? row.requirementStatus;
  const base = `/projects/${projectId}/requirements/${row.requirementId}/status`;
  const reasonOk = reason.trim().length > 0;

  const submit = async (action: 'decide' | 'revert') => {
    setSaving(action);
    try {
      if (action === 'decide') {
        await api.put<RequirementDetailResponse>(base, { status, reason: reason.trim() });
      } else {
        await api.post<RequirementDetailResponse>(`${base}/revert`, { reason: reason.trim() });
      }
      toast({
        title: action === 'decide' ? '상태를 지정했습니다.' : '근거대로 되돌렸습니다.',
        variant: 'success',
      });
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast({
        title: '저장하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(null);
    }
  };

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>요구사항 상태 지정</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{row.requirementCode}</span> {row.requirementTitle}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <dl className="bg-muted/40 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md px-3 py-2 text-sm">
            <dt className="text-muted-foreground">근거 상태</dt>
            <dd>{label(evidence)}</dd>
            <dt className="text-muted-foreground">지금 상태</dt>
            <dd>
              {label(row.requirementStatus)}
              {decision && <span className="text-primary"> · 발주기관 지정</span>}
            </dd>
            {decision && (
              <>
                <dt className="text-muted-foreground">지정 사유</dt>
                <dd className="break-keep">{decision.reason}</dd>
                <dt className="text-muted-foreground">지정</dt>
                <dd>
                  {decision.decidedBy ?? '알 수 없음'}
                  {decision.decidedByRole === 'SUPER_ADMIN' ? '(관리자)' : ''} ·{' '}
                  {formatDateTime(decision.decidedAt)}
                </dd>
              </>
            )}
          </dl>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="decision-status">지정할 상태</Label>
            <select
              id="decision-status"
              className="bg-background border-input h-9 rounded-md border px-2 text-sm"
              value={status}
              onChange={(e) => setStatus(e.target.value as RequirementStatus)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="decision-reason">사유 (필수)</Label>
            <Textarea
              id="decision-reason"
              rows={3}
              maxLength={1000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="예: 10-14 시연에서 근거 부족 시 답변 차단 동작을 확인함"
            />
            <p className="text-muted-foreground text-xs">
              사유와 지정한 사람은 변경 이력에 남고 용역사에게 알림이 갑니다. 다시 수집해도 지정한
              상태는 바뀌지 않습니다.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          {decision ? (
            <Button
              variant="outline"
              disabled={!reasonOk || saving !== null}
              onClick={() => void submit('revert')}
            >
              {saving === 'revert' ? '되돌리는 중…' : `근거대로 되돌리기 (${label(evidence)})`}
            </Button>
          ) : (
            <span />
          )}
          <Button disabled={!reasonOk || saving !== null} onClick={() => void submit('decide')}>
            {saving === 'decide' ? '저장 중…' : '지정'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
