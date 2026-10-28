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

/** 요구사항 화면 머리에 두는 기준선 상태. 확정 전이면 지금 목록이 기준선이 아니라고 알린다. */
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
              ` 명세서에 없던 기존 요구사항 ${state.outsideBaselineCount}건은 기준선 밖에 있습니다.`}
            {state.unresolvedCodeCount > 0 &&
              ` 커밋·이슈에 요구사항에 없는 ID 가 ${state.unresolvedCodeCount}개 적혀 있습니다.`}
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
            ? `지금 목록 ${state.requirementCount}건은 확정된 기준선이 아닙니다.`
            : '명세서를 등록해 요구사항 목록을 만드세요.'}
          {working ? ' 발주기관이 확정하면 명세서 목록으로 바뀝니다.' : ''}
        </AlertDescription>
      </div>
      {link}
    </Alert>
  );
}
