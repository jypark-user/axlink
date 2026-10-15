import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { formatDateTime } from '@/lib/format';
import type { BaselineStateResponse } from '@/types/api';

const WORKING_WORD: Record<string, string> = {
  DRAFT: '용역사 정리 중',
  SUBMITTED: '발주기관 확정 대기',
};

/** 요구사항 화면 머리에 두는 기준선 상태. 미등록·미확정이면 지금 목록이 무엇인지 같이 적는다. */
export function BaselineBanner({
  projectId,
  state,
}: {
  projectId: string;
  state: BaselineStateResponse;
}): ReactNode {
  const link = (
    <Button asChild size="sm" variant="outline">
      <Link to={`/p/${projectId}/requirement-baseline`}>기준선 보기</Link>
    </Button>
  );

  if (state.confirmed) {
    const c = state.confirmed;
    return (
      <Alert variant="success" className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <AlertTitle>
            요구사항 기준선 v{c.version} 확정 · {c.confirmedAt ? formatDateTime(c.confirmedAt) : ''}
          </AlertTitle>
          <AlertDescription>
            {c.sourceFilename}
            {c.sourceDocVersion ? ` (문서 v${c.sourceDocVersion})` : ''} 기준입니다.
            {state.outsideBaselineCount > 0 &&
              ` 기준선 밖 요구사항 ${state.outsideBaselineCount}건은 명세서에 없던 기존 항목입니다.`}
            {state.unresolvedCodeCount > 0 &&
              ` 명세서에 없는 ID 를 가리킨 근거 ${state.unresolvedCodeCount}종이 있습니다.`}
          </AlertDescription>
        </div>
        {link}
      </Alert>
    );
  }

  const working = state.workingStatus ? WORKING_WORD[state.workingStatus] : null;
  return (
    <Alert variant="warning" className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <AlertTitle>
          요구사항 기준선 미확정{working ? ` · ${working}` : ' · 명세서 미등록'}
        </AlertTitle>
        <AlertDescription>
          {state.requirementCount > 0
            ? `지금 목록 ${state.requirementCount}건은 확정된 기준선이 아니라 도구 이슈에서 만든 요구사항입니다.`
            : '확정된 요구사항이 없습니다.'}
          {working ? ' 명세서 목록은 발주기관이 확정한 뒤 여기에 반영됩니다.' : ''}
        </AlertDescription>
      </div>
      {link}
    </Alert>
  );
}
