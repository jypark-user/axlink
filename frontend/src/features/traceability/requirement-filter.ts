import { label } from '@/lib/labels';
import type {
  RequirementStatus,
  RequirementSummaryResponse,
  SourceState,
  SourceStateSummary,
} from '@/types/api';

/** 요약 카드를 누르면 걸리는 조건. 한 번에 하나만 건다. */
export type RequirementFilter =
  | { kind: 'all' }
  | { kind: 'verified'; value: boolean }
  | { kind: 'status'; status: RequirementStatus }
  | {
      kind: 'source';
      connectionId: string | null;
      sourceLabel: string;
      state: Exclude<SourceState, 'NONE'> | 'NONE';
    };

export const NO_FILTER: RequirementFilter = { kind: 'all' };

const SOURCE_STATE_WORD: Record<SourceState, string> = {
  OPEN: '출처 이슈 열림',
  CLOSED: '출처 이슈 닫힘',
  UNKNOWN: '출처 이슈 기록 없음',
  NONE: '출처 이슈 없음',
};

export function sourceStateWord(state: SourceState): string {
  return SOURCE_STATE_WORD[state];
}

/** 서버 목록 조건. 추적표 API 의 쿼리 이름과 같다. */
export function filterParams(filter: RequirementFilter): Record<string, string | boolean> {
  switch (filter.kind) {
    case 'all':
      return {};
    case 'verified':
      return { verified: filter.value };
    case 'status':
      return { status: filter.status };
    case 'source':
      return filter.connectionId
        ? { sourceState: filter.state, connectionId: filter.connectionId }
        : { sourceState: 'NONE' };
  }
}

/** 지금 걸린 조건을 사람 말로. 조건이 없으면 null. */
export function filterLabel(filter: RequirementFilter): string | null {
  switch (filter.kind) {
    case 'all':
      return null;
    case 'verified':
      return filter.value ? '검증 완료(검증·인수)' : '검증 미완료';
    case 'status':
      return `상태 ${label(filter.status)}`;
    case 'source':
      return filter.connectionId
        ? `${filter.sourceLabel} · ${sourceStateWord(filter.state)}`
        : filter.sourceLabel;
  }
}

/** 검증 완료 비율. 분모가 0 이면 나눌 수 없다. */
export function rateText(rate: number | null): string {
  return rate === null ? '산출 불가' : `${Math.round(rate * 1000) / 10}%`;
}

export function sameFilter(a: RequirementFilter, b: RequirementFilter): boolean {
  return JSON.stringify(filterParams(a)) === JSON.stringify(filterParams(b));
}

export function sourceFilter(
  s: SourceStateSummary,
  state: Exclude<SourceState, 'NONE'>,
): RequirementFilter {
  return { kind: 'source', connectionId: s.connectionId, sourceLabel: s.label, state };
}

/** '구현' 칸에 출처 이슈가 닫혀서 붙은 상태가 몇 건 들었는지. 실제 구현 확인과 구분한다. */
export function implementedNote(n: RequirementSummaryResponse): string {
  const implemented = n.byStatus.find((s) => s.status === 'IMPLEMENTED')?.count ?? 0;
  const head =
    n.implementedFromSourceClosed === implemented
      ? `구현 ${implemented}건은 모두`
      : `구현 ${implemented}건 중 ${n.implementedFromSourceClosed}건은`;
  return `${head} 출처 이슈가 닫혀서 '구현'이 된 것입니다. 실제 구현을 확인한 것은 아닙니다.`;
}
