import { useEffect, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Markdown } from '@/components/ui/markdown';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { ServerLink } from '@/components/common/server-link';
import { api } from '@/lib/http';
import { formatBytes, formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import { isProcessing, ProcessingBadge } from '@/features/documents/processing';
import type { DocumentDetailResponse, DocumentTextResponse } from '@/types/api';

/**
 * 자료 상세. 왼쪽은 정보, 오른쪽은 추출 결과다. 읽기만 한다.
 * 자료는 산출물과 별개 공간이다(11-19 사용자 결정). 여기서 WBS 작업에 붙이거나 산출물로 내지
 * 않는다. 초안 확인 화면도 없앴다. 산출물은 산출물 화면의 올리기로만 들어간다.
 */
export function DocumentDetailPage(): ReactNode {
  const { project } = useProjectContext();
  const { documentId = '' } = useParams();

  const detail = useAsync<DocumentDetailResponse>(
    () => api.get<DocumentDetailResponse>(`/documents/${documentId}`),
    [documentId],
  );
  const text = useAsync<DocumentTextResponse>(
    () => api.get<DocumentTextResponse>(`/documents/${documentId}/text`),
    [documentId],
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

  return (
    <DataState state={detail} onRetry={detail.reload}>
      {(doc) => (
        <>
          <PageHeader
        guide="deliverables#documents"
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
            {/* 왼쪽: 정보 */}
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
                <ServerLink
                  url={doc.downloadUrl}
                  filename={doc.fileName}
                  className="underline-offset-2 hover:underline"
                >
                  원본 파일 내려받기
                </ServerLink>
                {doc.originalUrl ? (
                  <a
                    href={doc.originalUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline-offset-2 hover:underline"
                  >
                    수집한 도구에서 보기
                  </a>
                ) : (
                  <span className="text-muted-foreground text-xs">
                    직접 올린 문서라 여기가 원본입니다. 도구에서 수집한 산출물에는 그 도구의 링크가
                    붙고, 폐쇄망에서는 그 링크가 열리지 않을 수 있습니다.
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
