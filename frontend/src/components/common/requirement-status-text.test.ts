import { describe, expect, it } from 'vitest';
import {
  requirementStatusText,
  SOURCE_ISSUE_CLOSED_NOTE,
} from '@/components/common/requirement-status-text';

describe('requirementStatusText', () => {
  it('GitHub 이슈 닫힘에서 온 상태는 그 사실과 뜻하지 않는 것을 함께 말한다', () => {
    expect(requirementStatusText('IMPLEMENTED', 'SOURCE_ISSUE_CLOSED')).toEqual({
      text: '원천 이슈 닫힘',
      note: SOURCE_ISSUE_CLOSED_NOTE,
    });
    expect(SOURCE_ISSUE_CLOSED_NOTE).toBe('구현·검증 완료를 뜻하지 않음');
  });

  it('출처 표시가 없는 상태는 GitHub 닫힘으로 설명하지 않는다', () => {
    expect(requirementStatusText('IMPLEMENTED', null)).toEqual({ text: '구현', note: null });
    expect(requirementStatusText('VERIFIED', undefined)).toEqual({ text: '검증', note: null });
    expect(requirementStatusText('DEFINED', null)).toEqual({ text: '정의', note: null });
  });
});
