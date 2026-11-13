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
  it('GitHub 은 필요한 읽기 권한 넷을 적는다', () => {
    const g = TOOL_GUIDE.GITHUB;
    for (const scope of ['Metadata', 'Issues', 'Pull requests', 'Contents', 'Read-only']) {
      expect(g.permission).toContain(scope);
    }
    expect(g.readOnly).toContain('아무것도 쓰지 않습니다');
  });

  it('Redmine 은 저장소·커밋·PR 대신 Redmine 의 말을 쓴다', () => {
    const text = Object.values(TOOL_GUIDE.REDMINE).join(' ');
    for (const word of ['저장소', '커밋', 'PR', '풀 리퀘스트']) {
      expect(text).not.toContain(word);
    }
    expect(text).toContain('REST 웹 서비스');
    expect(text).toContain('일감 보기');
    expect(TOOL_GUIDE.REDMINE.readOnly).toContain('아무것도 쓰지 않습니다');
  });
});
