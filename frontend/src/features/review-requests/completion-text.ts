import type { CompletionItem, CompletionStatus, EvidenceKind } from '@/types/api';

/**
 * 작업 완료 확인 화면의 말. 네 사실을 섞지 않는다.
 * 파일 대조는 '파일·문서가 있다'일 뿐 제출이 아니고, 승인은 산출물 버전에 붙는 것이며,
 * 작업 완료 확인만 발주기관이 작업 완료를 인정한 기록이다.
 */

export const FILE_CHECK_WORD: Record<string, string> = {
  MATCHED: '대조됨(파일·문서 있음)',
  MISSING: '대조 안 됨',
  OVERDUE: '대조 안 됨 · 기한 지남',
  NONE: '산출물 지정 없음',
};

export const SUBMISSION_WORD: Record<string, string> = {
  SUBMITTED: '제출됨',
  DRAFT: '초안',
  UNKNOWN: '미확인',
};

export const APPROVAL_WORD: Record<string, string> = {
  APPROVED: '승인',
  REJECTED: '반려',
  NOT_APPROVED: '미승인',
  UNKNOWN: '미확인',
};

export const COMPLETION_WORD: Record<CompletionStatus, string> = {
  CONFIRMED: '완료 확인됨',
  RECONFIRM: '재확인 필요(범위 변경)',
  WITHDRAWN: '확인 철회됨',
  NONE: '완료 확인 없음',
};

export const KEY_REASON_WORD: Record<string, string> = {
  RENAMED: '작업명이 바뀌어 같은 작업인지 확인할 수 없음',
  REAPPEARED: '빠졌다가 다시 들어온 번호',
  LEAF_CHANGED: '분할·병합으로 말단 여부가 바뀜',
  RESTRUCTURED: '형제 작업이 바뀌며 가중치가 옮겨 감',
  NEW: '새 작업',
};

export const EVIDENCE_KINDS: { value: EvidenceKind; label: string }[] = [
  { value: 'WORK_PRODUCT', label: '산출물 버전' },
  { value: 'DOCUMENT', label: '문서' },
  { value: 'FILE', label: '저장소 파일' },
  { value: 'COMMIT', label: '커밋·PR' },
  { value: 'TEST', label: '시험 결과' },
  { value: 'DEMO', label: '시연' },
  { value: 'MEETING', label: '회의 기록' },
  { value: 'OTHER', label: '기타' },
];

export const EVIDENCE_KIND_LABEL: Record<string, string> = Object.fromEntries(
  EVIDENCE_KINDS.map((k) => [k.value, k.label]),
);

/** 비율 표시. 분모가 없으면 0% 로 대신하지 않는다. */
export function rateText(rate: number | null): string {
  return rate === null ? '산출 불가' : `${Math.round(rate * 1000) / 10}%`;
}

/** 완료 확인 칸의 말. 승계되지 않은 예전 확인이 있으면 재확인 대상임을 밝힌다. */
export function completionText(item: CompletionItem): string {
  if (item.completionStatus === 'NONE' && item.predecessorConfirmed) {
    const why = KEY_REASON_WORD[item.keyReason] ?? '작업 식별 변경';
    return `재확인 필요(${why})`;
  }
  return COMPLETION_WORD[item.completionStatus];
}

/** 보고 실적이 100% 가 아닌 작업을 완료 확인할 때의 안내. 보고값은 바뀌지 않는다. */
export function ackWarning(actual: unknown): string | null {
  if (typeof actual !== 'number' || actual >= 1) return null;
  return `용역사 보고 실적은 ${Math.round(actual * 100)}% 입니다. 완료를 인정해도 보고 실적은 바뀌지 않습니다.`;
}
