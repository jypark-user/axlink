import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import {
  PM_ACTIVITIES,
  SI_PHASES,
  WORK_PRODUCT_TYPES,
  type DraftRequirement,
  type Priority,
  type StructuringConfirmResponse,
  type StructuringDraftResponse,
  type WorkProductStatus,
  type WorkProductType,
} from '@/types/api';

const PRIORITIES: Priority[] = ['MUST', 'SHOULD', 'COULD', 'WONT'];
/** 확정은 산출물 등록이다. 승인은 발주기관이 산출물 화면에서 따로 한다. */
const STATUSES: WorkProductStatus[] = ['DRAFT', 'SUBMITTED'];
const NONE = 'NONE';

export function StructuringDraftPage(): ReactNode {
  const { projectId, documentId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();

  const state = useAsync<StructuringDraftResponse>(
    () => api.get<StructuringDraftResponse>(`/documents/${documentId}/draft`),
    [documentId],
  );
  const draft = state.data;

  const [type, setType] = useState<string>('');
  const [title, setTitle] = useState('');
  const [version, setVersion] = useState('');
  const [authoredDate, setAuthoredDate] = useState('');
  const [pmActivity, setPmActivity] = useState<string>(NONE);
  const [siActivity, setSiActivity] = useState<string>(NONE);
  const [status, setStatus] = useState<WorkProductStatus>('DRAFT');
  const [requirements, setRequirements] = useState<DraftRequirement[]>([]);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!draft) return;
    setType(draft.suggestedType ?? '');
    setTitle(draft.title ?? '');
    setVersion(draft.version ?? '1.0');
    setAuthoredDate(draft.authoredDate ?? '');
    setPmActivity(draft.pmActivity ?? NONE);
    setSiActivity(draft.siActivity ?? NONE);
    setRequirements(draft.requirements);
  }, [draft]);

  const confirm = async () => {
    if (!type || !title.trim() || !version.trim() || requirements.length === 0) {
      toast({ title: '유형·제목·버전·요구사항은 필수입니다.', variant: 'error' });
      return;
    }
    setPending(true);
    try {
      const res = await api.post<StructuringConfirmResponse>(
        `/documents/${documentId}/draft/confirm`,
        {
          type: type as WorkProductType,
          title: title.trim(),
          version: version.trim(),
          authoredDate: authoredDate || null,
          pmActivity: pmActivity === NONE ? null : pmActivity,
          siActivity: siActivity === NONE ? null : siActivity,
          requirements,
          workProductStatus: status,
        },
      );
      toast({
        title: `확정했습니다. 요구사항 ${res.createdRequirementIds.length}건 생성.`,
        variant: 'success',
      });
      void navigate(`/p/${projectId}/documents`);
    } catch (e) {
      toast({
        title: '확정에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  const reject = async () => {
    await api.post<void>(`/documents/${documentId}/draft/reject`, {});
    void navigate(`/p/${projectId}/documents`);
  };

  return (
    <>
      <PageHeader title="요구사항 확인" description="문서에서 뽑은 내용을 확인하고 확정합니다." />
      <DataState state={state} onRetry={state.reload}>
        {(d) => (
          <div className="flex max-w-3xl flex-col gap-4">
            <div className="flex items-center gap-2">
              <Badge variant="outline">{label(d.status)}</Badge>
              <span className="text-sm text-muted-foreground">
                신뢰도 {(d.confidence * 100).toFixed(0)}%
              </span>
              {d.rejectedTypeRaw && (
                <span className="text-sm text-warning">추정 실패 유형: {d.rejectedTypeRaw}</span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="type">산출물 유형</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger id="type">
                  <SelectValue placeholder="유형 선택" />
                </SelectTrigger>
                <SelectContent>
                  {WORK_PRODUCT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="title">제목</Label>
                <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="version">버전</Label>
                <Input id="version" value={version} onChange={(e) => setVersion(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="authoredDate">작성일</Label>
                <Input
                  id="authoredDate"
                  type="date"
                  value={authoredDate}
                  onChange={(e) => setAuthoredDate(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="status">확정 상태</Label>
                <Select value={status} onValueChange={(v) => setStatus(v as WorkProductStatus)}>
                  <SelectTrigger id="status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {label(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-xs">
                  승인은 확정과 별도로 발주기관이 산출물 화면에서 합니다.
                </p>
              </div>
              <ActivitySelect
                id="pmActivity"
                title="PM 활동"
                value={pmActivity}
                options={[...PM_ACTIVITIES]}
                onChange={setPmActivity}
              />
              <ActivitySelect
                id="siActivity"
                title="SI 활동"
                value={siActivity}
                options={[...SI_PHASES]}
                onChange={setSiActivity}
              />
            </div>

            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-medium">추출 요구사항 {requirements.length}건</h2>
              {requirements.map((r, i) => (
                <div key={r.index} className="flex flex-col gap-2 rounded-md border p-3">
                  <div className="flex gap-2">
                    <Input
                      aria-label={`요구사항 ${i + 1} 제목`}
                      value={r.title}
                      onChange={(e) =>
                        setRequirements((prev) =>
                          prev.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)),
                        )
                      }
                    />
                    <Select
                      value={r.priority}
                      onValueChange={(v) =>
                        setRequirements((prev) =>
                          prev.map((x, j) => (j === i ? { ...x, priority: v as Priority } : x)),
                        )
                      }
                    >
                      <SelectTrigger className="w-32" aria-label={`요구사항 ${i + 1} 우선순위`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORITIES.map((p) => (
                          <SelectItem key={p} value={p}>
                            {label(p)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="outline"
                      onClick={() => setRequirements((prev) => prev.filter((_, j) => j !== i))}
                    >
                      삭제
                    </Button>
                  </div>
                  <Textarea
                    aria-label={`요구사항 ${i + 1} 본문`}
                    rows={2}
                    value={r.body}
                    onChange={(e) =>
                      setRequirements((prev) =>
                        prev.map((x, j) => (j === i ? { ...x, body: e.target.value } : x)),
                      )
                    }
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-2 pb-8">
              <Button onClick={confirm} disabled={pending}>
                확정
              </Button>
              <Button variant="outline" onClick={reject} disabled={pending}>
                반려
              </Button>
            </div>
          </div>
        )}
      </DataState>
    </>
  );
}

function ActivitySelect({
  id,
  title,
  value,
  options,
  onChange,
}: {
  id: string;
  title: string;
  value: string;
  options: string[];
  onChange: (next: string) => void;
}): ReactNode {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{title}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>없음</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
