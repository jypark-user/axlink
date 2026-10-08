import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import type { DocumentProcessingState } from '@/types/api';

/**
 * 문서 처리 작업 상태(GH-121). 업로드는 접수만 하고 읽기·색인·초안은 뒤에서 한다.
 * 동기화 작업의 QUEUED·RUNNING 라벨(대기·실행중)과 뜻이 달라 문서 화면 전용으로 둔다.
 */
const LABEL: Record<DocumentProcessingState, string> = {
  QUEUED: '접수됨',
  RUNNING: '처리 중',
  DONE: '완료',
  FAILED: '처리 실패',
};

export const isProcessing = (state: DocumentProcessingState | undefined): boolean =>
  state === 'QUEUED' || state === 'RUNNING';

export function ProcessingBadge({ state }: { state: DocumentProcessingState }): ReactNode {
  const variant = state === 'FAILED' ? 'destructive' : state === 'DONE' ? 'success' : 'info';
  return <Badge variant={variant}>{LABEL[state]}</Badge>;
}
