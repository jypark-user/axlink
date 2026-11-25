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

/**
 * 요구사항 화면 머리에 두는 목록 확정 상태(내부 이름은 기준선). 확정 전이면 지금 보이는 요구사항이
 * 확정된 목록이 아니라고 알린다. 화면 말은 "요구사항 목록 확정" 으로 쓴다.
 */
export function BaselineBanner({
  projectId,
  state,
}: {
  projectId: string;
  state: BaselineStateResponse;
}): ReactNode {
  const link = (
    <Button asChild size="sm" variant="outline">
      <Link to={`/p/${projectId}/requirement-baseline`}>요구사항 등록·확정</Link>
    </Button>
  );

  if (state.confirmed) {
    const c = state.confirmed;
    return (
      <Alert variant="success" className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <AlertTitle>
            확정된 요구사항 목록 · 확정본 v{c.version}
            {c.confirmedAt ? ` · ${formatDateTime(c.confirmedAt)} 확정` : ''}
          </AlertTitle>
          <AlertDescription>
            {c.sourceFilename}
            {c.sourceDocVersion ? ` (문서 v${c.sourceDocVersion})` : ''} 기준입니다.
            {state.outsideBaselineCount > 0 &&
              ` 확정된 명세서에 포함되지 않은 요구사항이 ${state.outsideBaselineCount}건 있습니다.`}
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
          요구사항 목록 확정 전{working ? ` · ${working}` : ' · 명세서 미등록'}
        </AlertTitle>
        <AlertDescription>
          {state.requirementCount > 0
            ? `지금 보이는 요구사항 ${state.requirementCount}건은 확정된 요구사항 목록이 아닙니다.`
            : '요구사항 명세서를 올려 용역사가 정리·제출하고 발주기관이 확정하면 목록이 생깁니다.'}
          {working
            ? ' 명세서에서 뽑은 확정 전 목록은 요구사항 등록·확정 화면에 있고, 발주기관이 확정하면 이 목록이 그것으로 바뀝니다.'
            : ''}
        </AlertDescription>
      </div>
      {link}
    </Alert>
  );
}
