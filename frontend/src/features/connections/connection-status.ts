import type { ConnectionStatus } from '@/types/api';

/**
 * 연결 상태의 말. 사업 상태 라벨 표(lib/labels)와 섞지 않는다 — ACTIVE 가 사업에서는 「진행」이지만
 * 연결에서는 「활성」이다. 「확인 전」·「활성」·「일시중지」는 IM-007 UC-010 의 말이다.
 */
export const CONNECTION_STATUS_LABEL: Record<ConnectionStatus, string> = {
  DRAFT: '확인 전',
  VERIFIED: '확인됨',
  ACTIVE: '활성',
  PAUSED: '일시중지',
  FAILED: '확인 실패',
};

export const connectionStatusLabel = (status: string): string =>
  CONNECTION_STATUS_LABEL[status as ConnectionStatus] ?? status;
