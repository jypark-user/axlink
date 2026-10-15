import type { ReactNode } from 'react';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { Markdown } from '@/components/ui/markdown';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type { HelpDocResponse } from '@/types/api';

/**
 * 도구 연동 가이드. 글은 화면에 두지 않고 납품 문서(docs/40-manual/도구-연동-가이드.md)를
 * /api/help 로 받아 그린다. 문서를 고치면 이 화면도 같이 바뀐다.
 * 사업 목록 메뉴와 도구 연동 화면 두 곳에서 연다.
 */
export function ToolIntegrationGuidePage(): ReactNode {
  const state = useAsync<HelpDocResponse>(
    () => api.get<HelpDocResponse>('/help/tool-integration'),
    [],
  );
  return (
    <DataState state={state} onRetry={state.reload}>
      {(doc) => (
        <>
          <PageHeader
            title={doc.title}
            description={`GitHub · Redmine 을 사업에 붙이는 방법입니다 · 문서 갱신 ${formatDateTime(doc.updatedAt)}`}
          />
          <article className="max-w-4xl pb-16">
            <Markdown>{doc.markdown}</Markdown>
          </article>
        </>
      )}
    </DataState>
  );
}
