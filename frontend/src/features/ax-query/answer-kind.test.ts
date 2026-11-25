import { describe, expect, it } from 'vitest';
import { answerKindLabel, routeLabel } from '@/features/ax-query/answer-kind';

describe('답 머리 표시', () => {
  it('경로는 내부 코드가 아니라 화면 이름으로 보인다', () => {
    expect(routeLabel('AI_JUDGE')).toBe('AI 판단');
    expect(routeLabel('AGGREGATE')).toBe('집계');
    expect(routeLabel('DOCUMENT')).toBe('문서 근거');
  });

  it('모르는 경로 코드는 그대로 내보내지 않는다', () => {
    expect(routeLabel('SOMETHING_NEW')).toBeNull();
    expect(routeLabel(null)).toBeNull();
  });

  it('답의 종류 이름은 그대로다', () => {
    expect(answerKindLabel('NUMBER_GUARD')).toBe('근거 없는 수치 문장 숨김');
  });
});
