import { describe, expect, it } from 'vitest';
import { conversationPath, scopeLabel } from '@/components/layout/conversation-link';
import type { ConversationResponse } from '@/types/api';

// 최근 질문에 사업명 라벨을 달고, 누르면 그 사업 메뉴로 들어간다(11-18 사용자 지시).

const conv = (scope: string[], names: string[]): ConversationResponse => ({
  id: 'c1',
  title: '이번 주 진척',
  projectScope: scope,
  projectNames: names,
  pinned: false,
  messageCount: 2,
  lastMessageAt: null,
  createdAt: '2026-11-18T00:00:00Z',
});

describe('최근 질문의 사업', () => {
  it('사업 하나면 이름, 여럿이면 「외 n」, 범위가 없으면 전체 사업', () => {
    expect(scopeLabel(conv(['p1'], ['JICA 사업']))).toBe('JICA 사업');
    expect(scopeLabel(conv(['p1', 'p2', 'p3'], ['가', '나', '다']))).toBe('가 외 2');
    expect(scopeLabel(conv([], []))).toBe('전체 사업');
  });

  it('사업 하나에서 한 질문은 그 사업 메뉴 안에서 연다', () => {
    expect(conversationPath(conv(['p1'], ['가']))).toBe('/p/p1/ask/c1');
    expect(conversationPath(conv(['p1'], ['가']), 'p2')).toBe('/p/p1/ask/c1');
  });

  it('여러 사업·전체 질문은 사업 밖에서 열고, 사업 안이면 그 자리에서 연다', () => {
    expect(conversationPath(conv(['p1', 'p2'], ['가', '나']))).toBe('/ask/c1');
    expect(conversationPath(conv([], []))).toBe('/ask/c1');
    expect(conversationPath(conv(['p1', 'p2'], ['가', '나']), 'p1')).toBe('/p/p1/ask/c1');
  });
});
