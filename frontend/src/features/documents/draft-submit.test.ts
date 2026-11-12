import { describe, expect, it } from 'vitest';
import { missingForSubmit } from './draft-submit';

describe('초안 산출물로 제출 전 확인', () => {
  it('요구사항이 0건이어도 유형·제목·버전이 있으면 낼 수 있다', () => {
    expect(missingForSubmit({ type: 'SOFTWARE_DESIGN', title: 'SW설계서', version: 'v1' })).toEqual(
      [],
    );
  });

  it('유형·제목·버전이 비면 빠진 항목을 알려 준다', () => {
    expect(missingForSubmit({ type: '', title: ' ', version: '' })).toEqual([
      '유형',
      '제목',
      '버전',
    ]);
  });
});
