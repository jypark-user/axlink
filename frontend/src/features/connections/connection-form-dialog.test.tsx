import { describe, expect, it } from 'vitest';
import { buildCredential, TOOL_GUIDE } from './connection-form-dialog';

describe('buildCredential', () => {
  it('requires a non-empty access token', () => {
    expect(buildCredential('')).toBeNull();
    expect(buildCredential('   ')).toBeNull();
  });

  it('trims the access token', () => {
    expect(buildCredential('  ghp_token  ')).toEqual({ accessToken: 'ghp_token' });
  });
});

describe('TOOL_GUIDE (AC-010-6)', () => {
  it('GitHub 은 읽기 전용과 토큰에 줄 읽기 권한 넷을 적는다', () => {
    for (const scope of [
      '읽기 전용',
      'Metadata',
      'Issues',
      'Pull requests',
      'Contents',
      'Read-only',
    ]) {
      expect(TOOL_GUIDE.GITHUB).toContain(scope);
    }
  });

  it('Redmine 은 저장소·커밋·PR 대신 Redmine 의 말을 쓴다', () => {
    const text = TOOL_GUIDE.REDMINE;
    for (const word of ['저장소', '커밋', 'PR', '풀 리퀘스트']) {
      expect(text).not.toContain(word);
    }
    for (const word of ['읽기 전용', 'REST 웹 서비스', '일감 보기']) {
      expect(text).toContain(word);
    }
  });
});
