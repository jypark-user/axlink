import { describe, expect, it } from 'vitest';
import { label } from '@/lib/labels';
import { connectionStatusLabel } from './connection-status';

describe('connectionStatusLabel', () => {
  it('연결 상태는 연결 전용 말로 쓴다', () => {
    expect(connectionStatusLabel('DRAFT')).toBe('확인 전');
    expect(connectionStatusLabel('VERIFIED')).toBe('확인됨');
    expect(connectionStatusLabel('ACTIVE')).toBe('활성');
    expect(connectionStatusLabel('PAUSED')).toBe('일시중지');
  });

  it('사업 상태 라벨 표와 갈린다', () => {
    expect(label('ACTIVE')).toBe('진행');
    expect(connectionStatusLabel('ACTIVE')).not.toBe(label('ACTIVE'));
  });

  it('모르는 상태는 원문 그대로 둔다', () => {
    expect(connectionStatusLabel('UNKNOWN')).toBe('UNKNOWN');
  });
});
