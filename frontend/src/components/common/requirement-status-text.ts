import { label } from '@/lib/labels';
import type { RequirementStatus, RequirementStatusBasis } from '@/types/api';

/** GitHub 이슈를 닫아 생긴 상태의 설명. 구현이나 검증을 누가 확인했다는 뜻이 아니다. */
export const SOURCE_ISSUE_CLOSED_NOTE = '구현·검증 완료를 뜻하지 않음';

/** 요구사항 상태 글자. 원천 이슈 닫힘에서 온 상태만 그 사실대로 부르고, 나머지는 상태 이름 그대로다. */
export function requirementStatusText(
  status: RequirementStatus,
  basis: RequirementStatusBasis | null | undefined,
): { text: string; note: string | null } {
  if (basis === 'SOURCE_ISSUE_CLOSED') {
    return { text: '원천 이슈 닫힘', note: SOURCE_ISSUE_CLOSED_NOTE };
  }
  return { text: label(status), note: null };
}
