import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Markdown } from '@/components/ui/markdown';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatBytes, formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import { isProcessing, ProcessingBadge } from '@/features/documents/processing';
import type {
  DocumentDetailResponse,
  DocumentTextResponse,
  WbsDeliverablesResponse,
  WorkProductChecklistResponse,
} from '@/types/api';

/**
 * 자료 상세. 왼쪽은 정보와 설정(WBS 항목·29110 유형 태그), 오른쪽은 추출 결과다.
 * 설정은 저장 즉시 반영되고 산출물 판정이 그것을 본다(ARC-016).
 */
export function DocumentDetailPage(): ReactNode {
  const { project } = useProjectContext();
  const { documentId = '' } = useParams();
  const { toast } = useToast();

  const detail = useAsync<DocumentDetailResponse>(
    () => api.get<DocumentDetailResponse>(`/documents/${documentId}`),
    [documentId],
  );
  const text = useAsync<DocumentTextResponse>(
    () => api.get<DocumentTextResponse>(`/documents/${documentId}/text`),
    [documentId],
  );
  // 고를 수 있는 WBS 항목과 유형. 둘 다 서버가 준다. 화면에 코드 목록을 박지 않는다.
  const wbs = useAsync<WbsDeliverablesResponse>(
    () => api.get<WbsDeliverablesResponse>(`/projects/${project.id}/wbs/deliverables`),
    [project.id],
  );
  const types = useAsync<WorkProductChecklistResponse>(
    () => api.get<WorkProductChecklistResponse>(`/projects/${project.id}/work-products`),
    [project.id],
  );

  // 접수됨·처리 중이면 끝날 때까지 다시 부른다. 처리는 뒤에서 한다(GH-121)
  const processing = isProcessing(detail.data?.processingState);
  const { reload: reloadDetail } = detail;
  const { reload: reloadText } = text;
  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => {
      reloadDetail();
      reloadText();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [processing, reloadDetail, reloadText]);

  const [wbsId, setWbsId] = useState('');
  const [productType, setProductType] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!detail.data) return;
    setWbsId(detail.data.wbsId ?? '');
    setProductType(detail.data.productType ?? detail.data.proposedType ?? '');
  }, [detail.data]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch<DocumentDetailResponse>(`/documents/${documentId}`, { wbsId, productType });
      toast({ title: '저장했습니다.', variant: 'success' });
      detail.reload();
    } catch (err) {
      toast({
        title: '저장하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  const typeLabel = (code: string | null): string => {
    if (!code) return '';
    const found = types.data?.items.find((t) => t.type === code);
    return found ? found.displayName : code;
  };

  return (
    <DataState state={detail} onRetry={detail.reload}>
      {(doc) => (
        <>
          <PageHeader
            title={doc.fileName}
            description={
              <span className="flex flex-wrap items-center gap-2">
                <Badge variant={badgeVariantFor(doc.status)}>{label(doc.status)}</Badge>
                {doc.processingState !== 'DONE' && <ProcessingBadge state={doc.processingState} />}
                <span className="text-muted-foreground text-sm">
                  {formatBytes(doc.fileSize)} · {doc.uploadedBy} · {formatDateTime(doc.uploadedAt)}
                </span>
              </span>
            }
            actions={
              <Button asChild size="sm" variant="outline">
                <Link to={`/p/${project.id}/documents`}>자료 목록</Link>
              </Button>
            }
          />

          <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
            {/* 왼쪽: 정보와 설정 */}
            <aside className="flex flex-col gap-5">
              {doc.processingError && (
                <p className="text-destructive rounded border border-destructive/30 p-3 text-sm">
                  {doc.processingError}
                </p>
              )}
              {!doc.processingError && doc.error && (
                <p className="text-destructive rounded border border-destructive/30 p-3 text-sm">
                  {doc.error}
                </p>
              )}
              {isProcessing(doc.processingState) && (
                <p className="text-muted-foreground rounded border p-3 text-sm">
                  {doc.processingState === 'QUEUED'
                    ? '접수했습니다. 앞 문서가 끝나면 읽기 시작합니다.'
                    : '읽고 색인하는 중입니다. 다른 화면을 써도 됩니다.'}
                  {stepsText(doc.processingSteps)}
                </p>
              )}

              <section className="flex flex-col gap-1 text-sm">
                <h2 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                  원본
                </h2>
                <a href={doc.downloadUrl} className="underline-offset-2 hover:underline">
                  원본 파일 내려받기
                </a>
                {doc.originalUrl ? (
                  <a
                    href={doc.originalUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline-offset-2 hover:underline"
                  >
                    원천 도구에서 보기
                  </a>
                ) : (
                  <span className="text-muted-foreground text-xs">
                    직접 올린 문서라 여기가 원본입니다. 도구에서 수집한 산출물은 원천 링크가 붙고,
                    폐쇄망에서는 그 링크가 열리지 않을 수 있습니다.
                  </span>
                )}
              </section>

              <section className="flex flex-col gap-1 text-sm">
                <h2 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                  추출
                </h2>
                <span className="tnum">
                  {doc.extractedCharCount !== null
                    ? `${doc.extractedCharCount.toLocaleString('ko-KR')}자`
                    : '아직 읽지 않음'}
                  {doc.pageCount !== null && ` · ${doc.pageCount}쪽`}
                </span>
                {doc.draftStatus === 'PROPOSED' && (
                  <Link
                    to={`/p/${project.id}/documents/${doc.id}/draft`}
                    className="underline-offset-2 hover:underline"
                  >
                    초안 확인 (요구사항·유형)
                  </Link>
                )}
                {doc.workProductId && (
                  <span className="text-muted-foreground text-xs">
                    확정되어 산출물 항목에 들어갔습니다.
                  </span>
                )}
              </section>

              <section className="flex flex-col gap-3 text-sm">
                <h2 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                  설정
                </h2>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="doc-wbs">WBS 항목</Label>
                  <select
                    id="doc-wbs"
                    className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                    value={wbsId}
                    onChange={(e) => setWbsId(e.target.value)}
                  >
                    <option value="">붙이지 않음</option>
                    {(wbs.data?.items ?? []).map((i) => (
                      <option key={i.wbsId} value={i.wbsId}>
                        {i.wbsId} {i.name}
                        {i.deliverable ? ` · ${i.deliverable}` : ''}
                      </option>
                    ))}
                  </select>
                  <span className="text-muted-foreground text-xs">
                    붙이면 그 항목의 산출물로 잡힙니다. 이름이 달라도 됩니다.
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="doc-type">산출물 유형 (ISO/IEC 29110)</Label>
                  <select
                    id="doc-type"
                    className="bg-background border-input h-9 rounded-md border px-2 text-sm"
                    value={productType}
                    onChange={(e) => setProductType(e.target.value)}
                  >
                    <option value="">정하지 않음</option>
                    {(types.data?.items ?? []).map((t) => (
                      <option key={t.type} value={t.type}>
                        {t.displayName}
                      </option>
                    ))}
                  </select>
                  <span className="text-muted-foreground text-xs">
                    분류 태그입니다. 단계별 집계에 쓰이고, 산출물 판정에는 영향이 없습니다.
                    {doc.proposedType && !doc.productType && (
                      <> AI 가 {typeLabel(doc.proposedType)}(으)로 추정했습니다.</>
                    )}
                  </span>
                </div>
                <div>
                  <Button size="sm" onClick={save} disabled={saving}>
                    {saving ? '저장 중…' : '저장'}
                  </Button>
                </div>
              </section>
            </aside>

            {/* 오른쪽: 추출 결과 */}
            <section className="min-w-0">
              <h2 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
                추출 결과
              </h2>
              <DataState
                state={text}
                onRetry={text.reload}
                empty={{ text: '추출된 글이 없습니다.' }}
              >
                {(t) =>
                  t.text.trim() ? (
                    <div className="rounded border p-4">
                      <Markdown className="text-sm leading-6">{t.text}</Markdown>
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-sm">추출된 글이 없습니다.</p>
                  )
                }
              </DataState>
            </section>
          </div>
        </>
      )}
    </DataState>
  );
}

/** 처리 단계에서 지금까지 알게 된 것. 쪽수·청크 수·걸린 시간 */
function stepsText(steps: Record<string, number | null> | null): string {
  if (!steps) return '';
  const bits: string[] = [];
  if (steps.pages) bits.push(`${steps.pages}쪽`);
  if (steps.chunks) bits.push(`조각 ${steps.chunks}개`);
  if (steps.extract_s != null) bits.push(`읽기 ${steps.extract_s}초`);
  if (steps.index_s != null) bits.push(`색인 ${steps.index_s}초`);
  return bits.length ? ` (${bits.join(' · ')})` : '';
}
