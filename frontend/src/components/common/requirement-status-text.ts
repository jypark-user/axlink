import { label } from '@/lib/labels';
import type { RequirementStatus, RequirementStatusBasis } from '@/types/api';

/** 출처 이슈가 닫혀 생긴 상태의 설명. 구현을 누가 확인했다는 뜻이 아니다. */
export const SOURCE_ISSUE_CLOSED_NOTE = '구현 확인 아님';

/** 발주기관이 사유와 함께 지정한 상태. 근거 상태는 따로 보인다. */
export const CLIENT_DECIDED_NOTE = '발주기관 지정';

/** 요구사항 상태 글자. 출처 이슈가 닫혀 생긴 상태만 그 사실대로 부르고, 나머지는 상태 이름 그대로다. */
export function requirementStatusText(
  status: RequirementStatus,
  basis: RequirementStatusBasis | null | undefined,
): { text: string; note: string | null } {
  if (basis === 'CLIENT_DECIDED') {
    return { text: label(status), note: CLIENT_DECIDED_NOTE };
  }
  if (basis === 'SOURCE_ISSUE_CLOSED') {
    return { text: '출처 이슈 닫힘', note: SOURCE_ISSUE_CLOSED_NOTE };
  }
  return { text: label(status), note: null };
}
