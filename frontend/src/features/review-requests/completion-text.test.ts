import { describe, expect, it } from 'vitest';
import { ackWarning, completionText, rateText } from '@/features/review-requests/completion-text';
import type { CompletionItem } from '@/types/api';

const item = (over: Partial<CompletionItem>): CompletionItem => ({
  wbsId: '1.1',
  taskKey: 'k',
  name: '착수보고',
  deliverable: null,
  weight: 0.2,
  reportedActual: 1,
  keyReason: 'CONTINUED',
  fileCheck: 'MATCHED',
  fileRef: null,
  submission: 'UNKNOWN',
  approval: 'UNKNOWN',
  productVersion: null,
  completionStatus: 'NONE',
  predecessorConfirmed: false,
  confirmedAt: null,
  confirmedBy: null,
  weightAtConfirm: null,
  planVersionAtConfirm: null,
  actualAtConfirm: null,
  evidenceRevised: false,
  openRequestId: null,
  openRequestStatus: null,
  ...over,
});

describe('완료 확인 문구', () => {
  it('분모가 없으면 산출 불가, 0 은 0%', () => {
    expect(rateText(null)).toBe('산출 불가');
    expect(rateText(0)).toBe('0%');
    expect(rateText(0.25)).toBe('25%');
  });

  it('식별을 잇지 못한 예전 확인은 재확인 대상으로 말한다', () => {
    expect(completionText(item({ predecessorConfirmed: true, keyReason: 'RENAMED' }))).toBe(
      '재확인 필요(작업명이 바뀌어 같은 작업인지 확인할 수 없음)',
    );
    expect(completionText(item({ completionStatus: 'RECONFIRM' }))).toBe('재확인 필요(범위 변경)');
    expect(completionText(item({}))).toBe('완료 확인 없음');
  });

  it('보고 100% 미만이면 보고값이 바뀌지 않는다고 알린다', () => {
    expect(ackWarning(0.5)).toBe(
      '용역사 보고 실적은 50% 입니다. 완료를 인정해도 보고 실적은 바뀌지 않습니다.',
    );
    expect(ackWarning(1)).toBeNull();
    expect(ackWarning(null)).toBeNull();
  });
});
