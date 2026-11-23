import type { ConversationResponse } from '@/types/api';

/**
 * 질문이 어느 사업에서 나왔는지. 사업 하나면 그 이름, 여럿이면 「첫 사업 외 n」,
 * 범위를 정하지 않은 질문은 접근 가능한 전체 사업을 본 것이다.
 */
export function scopeLabel(c: ConversationResponse): string {
  const names = c.projectNames;
  if (c.projectScope.length === 0 || names.length === 0) return '전체 사업';
  return names.length === 1 ? names[0] : `${names[0]} 외 ${names.length - 1}`;
}

/**
 * 사업 하나에서 한 질문은 그 사업 메뉴 안에서 연다(11-18 사용자 지시). 여러 사업이나 전체를 본
 * 질문은 사업 밖에서 연다. 사업 화면은 이어 묻는 질문의 범위를 그 사업 하나로 잡기 때문이다.
 */
export function conversationPath(c: ConversationResponse, currentProjectId?: string): string {
  const pid = c.projectScope.length === 1 ? c.projectScope[0] : undefined;
  if (pid) return `/p/${pid}/ask/${c.id}`;
  return currentProjectId ? `/p/${currentProjectId}/ask/${c.id}` : `/ask/${c.id}`;
}
