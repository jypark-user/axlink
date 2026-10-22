import { Fragment, useState, type ReactNode } from 'react';
import { BookOpen, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { Window } from '@/components/ui/window';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { useAuth } from '@/features/auth/auth-context';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { api } from '@/lib/http';
import { label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type {
  BaselineItem,
  BaselineMatch,
  BaselineParent,
  BaselineProblem,
  BaselineResponse,
  BaselineStateResponse,
  DocumentUploadResponse,
  PageResponse,
  Priority,
  UnresolvedRefResponse,
} from '@/types/api';

const PROBLEM_WORD: Record<BaselineProblem, string> = {
  DUPLICATE_CODE: '코드 중복',
  INVALID_CODE: '코드 형식 아님',
  MISSING_TITLE: '명칭 없음',
  UNTRACEABLE_CODE: '커밋·이슈가 참조할 수 없는 코드 형식',
};
const BLOCKING: BaselineProblem[] = ['DUPLICATE_CODE', 'INVALID_CODE', 'MISSING_TITLE'];
const MATCH_WORD: Record<BaselineMatch, string> = {
  NEW: '새 요구사항',
  SAME: '기존과 같음',
  CHANGED: '기존과 다름',
};
const STATUS_WORD = {
  DRAFT: '용역사 정리 중',
  SUBMITTED: '발주기관 확정 대기',
  CONFIRMED: '확정',
} as const;
const PRIORITIES: Priority[] = ['MUST', 'SHOULD', 'COULD', 'WONT'];
// 사용 설명서의 요구사항 등록 문서(docs/40-manual/요구사항-등록.md)
const GUIDE = '/guide/requirement-baseline';

/**
 * 요구사항 기준선 (GH-139). 용역사가 명세서를 등록·정리·제출하고 발주기관이 확정한다.
 * 확정 전 목록은 요구사항 화면·지표에 나오지 않는다.
 */
export function BaselinePage(): ReactNode {
  const { project } = useProjectContext();
  const { me } = useAuth();
  const base = `/projects/${project.id}/requirement-baseline`;
  const isAuthor = me?.role === 'CONTRACTOR' || me?.role === 'SUPER_ADMIN';
  const isConfirmer = me?.role === 'CLIENT' || me?.role === 'SUPER_ADMIN';

  const state = useAsync<BaselineStateResponse>(() => api.get<BaselineStateResponse>(base), [base]);
  const refs = useAsync<UnresolvedRefResponse[]>(
    () => api.get<UnresolvedRefResponse[]>(`/projects/${project.id}/requirements/unresolved-refs`),
    [project.id],
  );

  return (
    <>
      <PageHeader
        title="요구사항 기준선"
        description="용역사가 요구사항 명세서를 등록·정리해 제출하고, 발주기관이 확정합니다. 확정 전 목록은 요구사항 현황에 들어가지 않습니다."
        actions={
          <Button asChild variant="outline">
            <Link to={GUIDE}>
              <BookOpen className="size-4" /> 설명서
            </Link>
          </Button>
        }
      />
      <div className="flex flex-col gap-5">
        <DataState state={state} onRetry={state.reload}>
          {(s) => (
            <>
              {s.state === 'NONE' && (
                <NoBaseline
                  projectId={project.id}
                  base={base}
                  isAuthor={isAuthor}
                  s={s}
                  onChanged={state.reload}
                />
              )}
              {s.state !== 'CONFIRMED' && s.workingStatus === 'DRAFT' && !s.working && (
                <Alert>
                  <AlertTitle>용역사가 명세서를 정리하고 있습니다.</AlertTitle>
                  <AlertDescription>
                    제출하면 여기서 보고 확정하거나 돌려보낼 수 있습니다.
                  </AlertDescription>
                </Alert>
              )}
              {s.working && (
                <Working
                  b={s.working}
                  base={base}
                  isAuthor={isAuthor}
                  isConfirmer={isConfirmer}
                  onChanged={() => {
                    state.reload();
                    refs.reload();
                  }}
                />
              )}
              {s.confirmed && <ConfirmedBaseline base={base} summary={s.confirmed} />}
            </>
          )}
        </DataState>
        <UnresolvedRefs refs={refs.data ?? []} />
      </div>
    </>
  );
}

function NoBaseline({
  projectId,
  base,
  isAuthor,
  s,
  onChanged,
}: {
  projectId: string;
  base: string;
  isAuthor: boolean;
  s: BaselineStateResponse;
  onChanged: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [documentId, setDocumentId] = useState('');
  const [busy, setBusy] = useState(false);
  const docs = useAsync<PageResponse<DocumentUploadResponse>>(
    () =>
      isAuthor
        ? api.get<PageResponse<DocumentUploadResponse>>(
            `/projects/${projectId}/documents${toQueryString({ page: 0, size: 100 })}`,
          )
        : Promise.resolve({ content: [] } as unknown as PageResponse<DocumentUploadResponse>),
    [projectId, isAuthor],
  );
  const readable = (docs.data?.content ?? []).filter(
    (d) => (d.extractedCharCount ?? 0) > 0 && d.status !== 'FAILED',
  );

  const create = async () => {
    setBusy(true);
    try {
      await api.post<BaselineResponse>(base, { documentId });
      onChanged();
    } catch (err) {
      toast({
        title: '등록하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Window
      title="요구사항 기준선 미등록"
      hint={
        s.requirementCount > 0
          ? `지금 요구사항 ${s.requirementCount}건은 도구 이슈에서 만든 것입니다. 기준선을 확정하면 코드가 같은 항목에 붙고, 이슈로 요구사항을 만드는 설정은 꺼집니다.`
          : '확정된 요구사항이 없습니다.'
      }
    >
      {isAuthor ? (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-72 flex-col gap-1.5">
            <Label htmlFor="spec-doc">요구사항 명세서</Label>
            <Select value={documentId} onValueChange={setDocumentId}>
              <SelectTrigger id="spec-doc" className="w-full">
                <SelectValue placeholder="관련자료에 올린 문서에서 고르기" />
              </SelectTrigger>
              <SelectContent>
                {readable.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.fileName} · {formatDateTime(d.uploadedAt)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button disabled={!documentId || busy} onClick={create}>
            명세서로 등록
          </Button>
          {readable.length === 0 && !docs.loading && (
            <p className="text-muted-foreground text-sm">
              관련자료 화면에서 명세서 파일을 먼저 올려 주세요.
            </p>
          )}
          <SpecCautions />
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">
          용역사가 요구사항 명세서를 등록하고 제출하면 여기서 확정합니다.{' '}
          <Link to={`${GUIDE}#flow`} className="text-primary hover:underline">
            등록·확정 흐름
          </Link>
        </p>
      )}
    </Window>
  );
}

/** 명세서를 고르기 전에 보는 주의. 자세한 형식표는 설명서에 둔다. */
function SpecCautions(): ReactNode {
  return (
    <Alert className="mt-2 w-full">
      <AlertTitle>등록 전에 명세서 형식을 확인하세요</AlertTitle>
      <AlertDescription>
        <ul className="ml-4 list-disc space-y-1">
          <li>
            한 행에 요구사항 하나가 있는 표(ID 열과 내용 열)를 읽습니다. ID 는{' '}
            <code>SWFR.CON.004</code> · <code>REQ-001</code> 꼴이어야 합니다.
          </li>
          <li>
            숫자만 쓴 ID, 요구사항마다 세로 표를 쓰는 카드형, 머리행 위에 안내 행이 있는 표, 스캔한
            PDF 는 아직 읽지 못합니다. 등록한 뒤 항목을 직접 넣으세요.
          </li>
          <li>확정하면 되돌리기 어렵습니다. 처음이면 시험 사업에서 먼저 해 보세요.</li>
        </ul>
        <Link
          to={`${GUIDE}#spec-format`}
          className="text-primary mt-2 inline-block hover:underline"
        >
          명세서 형식 자세히 보기
        </Link>
      </AlertDescription>
    </Alert>
  );
}

function Working({
  b,
  base,
  isAuthor,
  isConfirmer,
  onChanged,
}: {
  b: BaselineResponse;
  base: string;
  isAuthor: boolean;
  isConfirmer: boolean;
  onChanged: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [editing, setEditing] = useState<BaselineItem | 'new' | null>(null);
  const [dialog, setDialog] = useState<'return' | 'confirm' | null>(null);
  const editable = isAuthor && b.status === 'DRAFT';
  const url = `${base}/${b.id}`;

  const run = async (action: () => Promise<unknown>, ok: string) => {
    try {
      await action();
      toast({ title: ok, variant: 'success' });
      onChanged();
    } catch (err) {
      toast({
        title: '처리하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <>
      <Window
        title={`기준선 v${b.version} · ${STATUS_WORD[b.status]}`}
        hint={<BaselineMeta b={b} />}
        action={
          <div className="flex flex-wrap gap-2">
            {editable && (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => run(() => api.del(url), '버렸습니다.')}
                >
                  등록 취소
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing('new')}>
                  항목 추가
                </Button>
                <Button
                  size="sm"
                  disabled={b.blockingCount > 0 || b.items.length === 0}
                  onClick={() => run(() => api.post(`${url}/submit`), '제출했습니다.')}
                >
                  제출
                </Button>
              </>
            )}
            {isConfirmer && b.status === 'SUBMITTED' && (
              <>
                <Button size="sm" variant="outline" onClick={() => setDialog('return')}>
                  돌려보내기
                </Button>
                <Button size="sm" onClick={() => setDialog('confirm')}>
                  확정
                </Button>
              </>
            )}
          </div>
        }
      >
        {b.returnedReason && b.status === 'DRAFT' && (
          <Alert variant="warning" className="mb-3">
            <AlertTitle>발주기관이 돌려보냈습니다</AlertTitle>
            <AlertDescription>{b.returnedReason}</AlertDescription>
          </Alert>
        )}
        {b.extractionEmpty && (
          <Alert variant="destructive" className="mb-3">
            <AlertTitle>명세서에서 요구사항을 찾지 못했습니다</AlertTitle>
            <AlertDescription>
              요구사항 ID 열이 있는 표나 코드로 시작하는 줄이 있어야 합니다. 항목을 직접 더하거나
              등록을 취소하고 다른 파일을 고르세요.{' '}
              <Link to={`${GUIDE}#spec-format`} className="text-primary hover:underline">
                읽는 명세서 형식
              </Link>
            </AlertDescription>
          </Alert>
        )}
        {b.blockingCount > 0 && (
          <p className="text-destructive mb-3 text-sm">
            제출 전에 고칠 항목이 {b.blockingCount}건 있습니다(코드 중복·코드 형식·명칭 없음).
          </p>
        )}
        <Summary b={b} />
        <ItemsTable
          items={b.items}
          parents={b.parents}
          editable={editable}
          onEdit={setEditing}
          onDelete={(item) => run(() => api.del(`${url}/items/${item.id}`), '항목을 지웠습니다.')}
        />
      </Window>
      <ImpactPanel b={b} />

      {editing && (
        <ItemDialog
          item={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSave={(body) =>
            run(
              () =>
                editing === 'new'
                  ? api.post(`${url}/items`, body)
                  : api.put(`${url}/items/${editing.id}`, body),
              '저장했습니다.',
            ).then(() => setEditing(null))
          }
        />
      )}
      {dialog === 'return' && (
        <ReturnDialog
          onClose={() => setDialog(null)}
          onSubmit={(reason) =>
            run(() => api.post(`${url}/return`, { reason }), '돌려보냈습니다.').then(() =>
              setDialog(null),
            )
          }
        />
      )}
      {dialog === 'confirm' && (
        <ConfirmDialog
          b={b}
          onClose={() => setDialog(null)}
          onSubmit={(applySpecCodes) =>
            run(
              () => api.post(`${url}/confirm`, { applySpecCodes }),
              '요구사항 기준선을 확정했습니다.',
            ).then(() => setDialog(null))
          }
        />
      )}
    </>
  );
}

function BaselineMeta({ b }: { b: BaselineResponse }): ReactNode {
  return (
    <span>
      {b.sourceFilename}
      {b.sourceDocVersion ? ` (문서 v${b.sourceDocVersion})` : ''} · 등록 {b.createdBy ?? '-'}{' '}
      {formatDateTime(b.createdAt)}
      {b.submittedAt ? ` · 제출 ${b.submittedBy ?? '-'} ${formatDateTime(b.submittedAt)}` : ''}
      {b.confirmedAt
        ? ` · 확정 ${b.confirmedBy ?? '-'}${b.confirmedByRole === 'SUPER_ADMIN' ? '(관리자)' : ''} ${formatDateTime(b.confirmedAt)}`
        : ''}
    </span>
  );
}

/** 기준선 한눈 요약. 요구사항 수와 기존 요구사항과의 대조. */
function Summary({ b }: { b: BaselineResponse }): ReactNode {
  if (b.items.length === 0) return null;
  const confirmed = b.status === 'CONFIRMED';
  const facts: [string, number][] = [['요구사항', b.items.length]];
  if (b.parents.length > 0) facts.push(['상위 요구사항', b.parents.length]);
  facts.push(
    [confirmed ? '새로 생김' : '새로 생길 것', b.counts.NEW],
    ['기존과 같음', b.counts.SAME],
    ['기존과 다름', b.counts.CHANGED],
  );
  return (
    <dl className="mb-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
      {facts.map(([name, n]) => (
        <div key={name} className="flex items-baseline gap-1.5">
          <dt className="text-muted-foreground">{name}</dt>
          <dd className="font-semibold tabular-nums">{n}건</dd>
        </div>
      ))}
    </dl>
  );
}

const NO_PARENT = '';

/** 항목을 상위 요구사항별로 묶는다. 상위가 없는 명세서는 한 묶음이다. 순서는 명세서 순서. */
function groupByParent(
  items: BaselineItem[],
  parents: BaselineParent[],
): { parent: BaselineParent | null; items: BaselineItem[] }[] {
  if (parents.length === 0) return [{ parent: null, items }];
  const owner = new Map<string, string>();
  for (const p of parents) for (const c of p.children) owner.set(c, p.code);
  const groups = new Map<string, BaselineItem[]>(parents.map((p) => [p.code, []]));
  groups.set(NO_PARENT, []);
  for (const item of items) {
    groups.get((item.code && owner.get(item.code)) || NO_PARENT)?.push(item);
  }
  return [
    ...parents.map((p) => ({ parent: p, items: groups.get(p.code) ?? [] })),
    { parent: null, items: groups.get(NO_PARENT) ?? [] },
  ].filter((g) => g.items.length > 0);
}

function ItemsTable({
  items,
  parents,
  editable,
  onEdit,
  onDelete,
}: {
  items: BaselineItem[];
  parents: BaselineParent[];
  editable: boolean;
  onEdit?: (item: BaselineItem) => void;
  onDelete?: (item: BaselineItem) => void;
}): ReactNode {
  if (items.length === 0) return null;
  const groups = groupByParent(items, parents);
  const columns = editable ? 5 : 4;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-40">요구사항 ID</TableHead>
          <TableHead>명칭</TableHead>
          <TableHead className="w-20">중요도</TableHead>
          <TableHead className="w-44">기존 요구사항과 대조</TableHead>
          {editable && <TableHead className="w-28" />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((g) => (
          <Fragment key={g.parent?.code ?? NO_PARENT}>
            {parents.length > 0 && (
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableCell colSpan={columns} className="py-2">
                  {g.parent ? (
                    <span className="text-sm">
                      <span className="text-muted-foreground font-mono text-xs">
                        {g.parent.code}
                      </span>{' '}
                      <span className="font-medium">{g.parent.title}</span>
                      <span className="text-muted-foreground"> · {g.items.length}건</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground text-sm">
                      상위 요구사항을 적지 않은 항목 · {g.items.length}건
                    </span>
                  )}
                </TableCell>
              </TableRow>
            )}
            {g.items.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                editable={editable}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  );
}

function ItemRow({
  item,
  editable,
  onEdit,
  onDelete,
}: {
  item: BaselineItem;
  editable: boolean;
  onEdit?: (item: BaselineItem) => void;
  onDelete?: (item: BaselineItem) => void;
}): ReactNode {
  const notes = [item.edited && '고침', item.origin === 'MANUAL' && '직접 추가'].filter(Boolean);
  return (
    <TableRow>
      <TableCell className="align-top">
        <span className="font-mono text-xs">{item.code ?? '(없음)'}</span>
        {item.location && (
          <div className="text-muted-foreground mt-0.5 text-xs">명세서 {item.location}</div>
        )}
        {item.problems.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {item.problems.map((p) => (
              <Badge key={p} variant={BLOCKING.includes(p) ? 'destructive' : 'warning'}>
                {PROBLEM_WORD[p]}
              </Badge>
            ))}
          </div>
        )}
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <span className="line-clamp-2 break-keep" title={item.title}>
          {item.title || '-'}
        </span>
        {notes.length > 0 && (
          <span className="text-muted-foreground text-xs">{notes.join(' · ')}</span>
        )}
      </TableCell>
      <TableCell className="align-top">{label(item.priority)}</TableCell>
      <TableCell className="align-top whitespace-normal text-xs">
        {item.match === 'NEW' && <span className="text-muted-foreground">{MATCH_WORD.NEW}</span>}
        {item.match && item.match !== 'NEW' && (
          <Badge variant={item.match === 'CHANGED' ? 'warning' : 'muted'}>
            {MATCH_WORD[item.match]}
          </Badge>
        )}
        {item.existing && item.match === 'CHANGED' && (
          <div className="text-muted-foreground mt-1">
            기존: {item.existing.title} · {label(item.existing.priority)} ({item.existing.source})
          </div>
        )}
        {item.specApplied && <div className="text-primary mt-1">명세서 내용으로 바꿈</div>}
      </TableCell>
      {editable && (
        <TableCell className="text-right align-top">
          <Button size="sm" variant="ghost" onClick={() => onEdit?.(item)}>
            고치기
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onDelete?.(item)}>
            지우기
          </Button>
        </TableCell>
      )}
    </TableRow>
  );
}

/** 확정하면 무엇이 바뀌는지. 기존 요구사항과의 대조, 명세서에 없는 기존 코드, 생성을 끌 연결. */
function ImpactPanel({ b }: { b: BaselineResponse }): ReactNode {
  const confirmed = b.status === 'CONFIRMED';
  return (
    <Window
      title={confirmed ? '확정 결과' : '확정하면'}
      hint="기존 요구사항은 ID·추적 링크·상태 지정·이력이 그대로입니다."
    >
      <div className="flex flex-col gap-3 text-sm">
        <div>
          <p className="font-medium">명세서에 없는 기존 요구사항 {b.missing.length}건</p>
          <p className="text-muted-foreground">
            지우지 않고 기준선 밖으로 둡니다. 정리는 변경 관리에서 합니다.
          </p>
          {b.missing.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {b.missing.map((m) => (
                <li key={m.requirementId}>
                  <span className="font-mono text-xs">{m.code}</span> {m.title} ({m.source})
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="font-medium">
            {confirmed ? '요구사항 생성을 끈 연결' : '이슈로 요구사항을 만드는 설정을 끌 연결'}{' '}
            {b.connections.length}개
          </p>
          {b.connections.length > 0 && (
            <p className="text-muted-foreground">
              {b.connections.map((c) => c.name).join(', ')}. 이후 이슈는 요구사항 ID 를 참조만
              합니다.
            </p>
          )}
        </div>
      </div>
    </Window>
  );
}

function ConfirmedBaseline({
  base,
  summary,
}: {
  base: string;
  summary: BaselineResponse;
}): ReactNode {
  const detail = useAsync<BaselineResponse>(
    () => api.get<BaselineResponse>(`${base}/${summary.id}`),
    [base, summary.id],
  );
  return (
    <DataState state={detail} onRetry={detail.reload}>
      {(b) => (
        <>
          <Window title={`기준선 v${b.version} · 확정`} hint={<BaselineMeta b={b} />}>
            <Summary b={b} />
            <ItemsTable items={b.items} parents={b.parents} editable={false} />
          </Window>
          <ImpactPanel b={b} />
        </>
      )}
    </DataState>
  );
}

function ItemDialog({
  item,
  onClose,
  onSave,
}: {
  item: BaselineItem | null;
  onClose: () => void;
  onSave: (body: { code: string; title: string; body: string; priority: Priority }) => void;
}): ReactNode {
  const [code, setCode] = useState(item?.code ?? '');
  const [title, setTitle] = useState(item?.title ?? '');
  const [body, setBody] = useState(item?.body ?? '');
  const [priority, setPriority] = useState<Priority>(item?.priority ?? 'SHOULD');
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item ? '명세서 항목 고치기' : '명세서 항목 추가'}</DialogTitle>
          <DialogDescription>
            {item?.location ? `명세서 ${item.location}. ` : ''}추출한 원래 값은 따로 남습니다.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-code">요구사항 ID</Label>
            <Input id="b-code" value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-title">명칭</Label>
            <Input id="b-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-body">설명</Label>
            <Textarea id="b-body" rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-priority">중요도</Label>
            <Select value={priority} onValueChange={(v) => setPriority(v as Priority)}>
              <SelectTrigger id="b-priority">
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
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={!title.trim()} onClick={() => onSave({ code, title, body, priority })}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReturnDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (reason: string) => void;
}): ReactNode {
  const [reason, setReason] = useState('');
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>용역사에 돌려보내기</DialogTitle>
          <DialogDescription>
            고칠 점을 적어 주세요. 용역사 화면에 그대로 보입니다.
          </DialogDescription>
        </DialogHeader>
        <Textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={!reason.trim()} onClick={() => onSubmit(reason.trim())}>
            돌려보내기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDialog({
  b,
  onClose,
  onSubmit,
}: {
  b: BaselineResponse;
  onClose: () => void;
  onSubmit: (applySpecCodes: string[]) => void;
}): ReactNode {
  const changed = b.items.filter((i) => i.match === 'CHANGED' && i.code);
  const [apply, setApply] = useState<string[]>([]);
  const toggle = (code: string) =>
    setApply((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>요구사항 기준선 v{b.version} 확정</DialogTitle>
          <DialogDescription>
            새 요구사항 {b.counts.NEW}건이 생기고, 기존 요구사항 {b.counts.SAME + b.counts.CHANGED}
            건은 ID 그대로 기준선에 붙습니다. 연결 {b.connections.length}개의 요구사항 생성 설정이
            꺼집니다. 확정한 뒤의 변경은 변경 관리 절차로 합니다.
          </DialogDescription>
        </DialogHeader>
        {changed.length > 0 && (
          <div className="flex max-h-80 flex-col gap-2 overflow-y-auto text-sm">
            <p className="font-medium">
              내용이 다른 기존 요구사항 {changed.length}건. 고르지 않으면 기존 정의를 둡니다.
            </p>
            {changed.map((i) => (
              <label key={i.id} className="flex items-start gap-2 rounded-md border px-3 py-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={apply.includes(i.code as string)}
                  onChange={() => toggle(i.code as string)}
                />
                <span>
                  <span className="font-mono text-xs">{i.code}</span> 명세서로 바꾸기
                  <br />
                  <span className="text-muted-foreground">
                    기존: {i.existing?.title} · {label(i.existing?.priority ?? 'SHOULD')}
                  </span>
                  <br />
                  명세서: {i.title} · {label(i.priority)}
                </span>
              </label>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => onSubmit(apply)}>확정</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 같은 코드를 가리킨 근거를 한 줄로 모은다. 코드는 서버 순서, 근거는 출처 번호순(GH-3, GH-12). */
function byCode(refs: UnresolvedRefResponse[]): [string, UnresolvedRefResponse[]][] {
  const out = new Map<string, UnresolvedRefResponse[]>();
  for (const r of refs) out.set(r.code, [...(out.get(r.code) ?? []), r]);
  const order = (a: UnresolvedRefResponse, b: UnresolvedRefResponse) =>
    a.sourceLabel.localeCompare(b.sourceLabel, 'ko', { numeric: true });
  return [...out.entries()].map(([code, rows]) => [code, rows.sort(order)]);
}

function RefSources({ refs }: { refs: UnresolvedRefResponse[] }): ReactNode {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {refs.map((r) => {
        const name = r.sourceLabel.length > 40 ? `${r.sourceLabel.slice(0, 39)}…` : r.sourceLabel;
        return r.evidenceUrl ? (
          <a
            key={`${r.sourceType}-${r.sourceId}`}
            className="text-primary inline-flex items-center gap-1 hover:underline"
            href={r.evidenceUrl}
            target="_blank"
            rel="noreferrer"
            title={r.evidenceText ?? r.sourceLabel}
          >
            {name} <ExternalLink className="size-3" />
          </a>
        ) : (
          <span key={`${r.sourceType}-${r.sourceId}`} title={r.evidenceText ?? undefined}>
            {name}
          </span>
        );
      })}
    </div>
  );
}

function RefTable({
  groups,
  first,
}: {
  groups: [string, UnresolvedRefResponse[]][];
  first: string;
}): ReactNode {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-64">{first}</TableHead>
          <TableHead className="w-16 text-right">근거</TableHead>
          <TableHead>가리킨 곳</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map(([code, rows]) => (
          <TableRow key={code}>
            <TableCell className="align-top">
              <span className="font-mono text-xs">{code}</span>
              {rows[0].parentTitle && (
                <div className="text-muted-foreground mt-0.5 text-xs">{rows[0].parentTitle}</div>
              )}
            </TableCell>
            <TableCell className="text-right align-top tabular-nums">{rows.length}건</TableCell>
            <TableCell className="align-top whitespace-normal text-xs">
              <RefSources refs={rows} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/**
 * 커밋·이슈가 가리켰지만 요구사항 목록에 없는 코드. 명세서의 상위 요구사항을 가리킨 것은
 * 정상이라 따로 접어 두고, 정말 없는 코드(오타·빠진 요구사항)를 앞에 둔다.
 */
function UnresolvedRefs({ refs }: { refs: UnresolvedRefResponse[] }): ReactNode {
  const unknown = byCode(refs.filter((r) => !r.parentTitle));
  const parents = byCode(refs.filter((r) => r.parentTitle));
  if (unknown.length === 0 && parents.length === 0) return null;
  const parentRefCount = parents.reduce((n, [, rows]) => n + rows.length, 0);
  return (
    <>
      {unknown.length > 0 && (
        <Window
          title={`요구사항 목록에 없는 ID ${unknown.length}종`}
          hint="커밋·이슈가 가리켰지만 사업 요구사항에도, 명세서의 상위 요구사항에도 없는 코드입니다. 추적 링크로 잇지 않습니다. 오타이거나 기준선에 빠진 요구사항입니다."
        >
          <RefTable groups={unknown} first="가리킨 ID" />
        </Window>
      )}
      {parents.length > 0 && (
        <Window
          title={`상위 요구사항을 가리킨 참조 ${parents.length}종`}
          hint="명세서 절 제목의 상위 요구사항 코드를 커밋·이슈가 적은 것입니다. 정상이며, 상위는 요구사항 목록에 들지 않으므로 추적 링크로 잇지 않습니다."
        >
          <details className="group">
            <summary className="text-muted-foreground cursor-pointer text-sm select-none">
              근거 {parentRefCount}건 보기
            </summary>
            <div className="mt-3">
              <RefTable groups={parents} first="상위 요구사항" />
            </div>
          </details>
        </Window>
      )}
    </>
  );
}
