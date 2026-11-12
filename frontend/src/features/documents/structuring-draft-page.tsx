import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
import { missingForSubmit } from './draft-submit';
import { useAsync } from '@/lib/use-async';
import {
  WORK_PRODUCT_TYPES,
  type DraftRequirement,
  type Priority,
  type StructuringConfirmResponse,
  type StructuringDraftResponse,
  type WorkProductType,
} from '@/types/api';

const PRIORITIES: Priority[] = ['MUST', 'SHOULD', 'COULD', 'WONT'];

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
  const [asking, setAsking] = useState(false);
  const [requirements, setRequirements] = useState<DraftRequirement[]>([]);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!draft) return;
    setType(draft.suggestedType ?? '');
    setTitle(draft.title ?? '');
    setVersion(draft.version ?? '1.0');
    setAuthoredDate(draft.authoredDate ?? '');
    setRequirements(draft.requirements);
  }, [draft]);

  /** 확정 = 산출물 제출(DEC-14). 뜻을 알리는 확인을 한 번 거친다 */
  const ask = () => {
    const missing = missingForSubmit({ type, title, version });
    if (missing.length > 0) {
      toast({ title: `${missing.join('·')}은 필수입니다.`, variant: 'error' });
      return;
    }
    setAsking(true);
  };

  const confirm = async () => {
    setAsking(false);
    setPending(true);
    try {
      await api.post<StructuringConfirmResponse>(
        `/documents/${documentId}/draft/confirm`,
        {
          type: type as WorkProductType,
          title: title.trim(),
          version: version.trim(),
          authoredDate: authoredDate || null,
          requirements,
        },
      );
      toast({
        title: `${title.trim()} ${version.trim()} 제출본으로 등록했습니다.`,
        description: '발주기관 검토 대상입니다.',
        variant: 'success',
      });
      void navigate(`/p/${projectId}/documents`);
    } catch (e) {
      toast({
        title: '제출에 실패했습니다.',
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
              <p className="text-muted-foreground text-xs sm:col-span-2">
                「산출물로 제출」하면 이 문서가 산출물 제출본(상태 「제출」)이 됩니다. 승인은
                발주기관이 산출물 화면에서 따로 합니다. 제출하지 않을 문서는 반려하고 자료로만
                두세요.
              </p>
            </div>

            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-medium">추출 요구사항 {requirements.length}건</h2>
              {requirements.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  이 문서에서 뽑은 요구사항이 없습니다. 산출물 제출에는 지장이 없습니다.
                  요구사항은 요구사항 명세서 등록으로 들어갑니다.
                </p>
              )}
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
              <Button onClick={ask} disabled={pending}>
                산출물로 제출
              </Button>
              <Button variant="outline" onClick={reject} disabled={pending}>
                반려
              </Button>
            </div>
          </div>
        )}
      </DataState>
      <AlertDialog open={asking} onOpenChange={setAsking}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>산출물로 제출할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              이 문서를 {title.trim()} {version.trim()} 제출본으로 등록합니다. 발주기관 검토
              대상이 됩니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirm()} disabled={pending}>
              제출
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
