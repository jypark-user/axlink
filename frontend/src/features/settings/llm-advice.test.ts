import { describe, expect, it } from 'vitest';
import { adviseNumPredict } from '@/features/settings/llm-advice';

describe('adviseNumPredict', () => {
  it('실사고 재현: 16000 · 18.6 tok/s · 600초면 504 경고다', () => {
    const a = adviseNumPredict({ rate: 18.6, predict: 16000, limit: 600 });
    expect(a.level).toBe('warn');
    // 예산 450초 × 18.6 = 8370 → 천 단위로 내림
    expect(a.advised).toBe(8000);
    expect(Math.ceil(a.worstSeconds ?? 0)).toBe(861);
    expect(a.text).toContain('⚠');
    expect(a.text).toContain('권장 8,000 이하');
    expect(a.text).toContain('최악 861초');
    expect(a.text).toContain('600초 상한을 넘겨');
    // 올리라는 시간 제한은 최악 + 예비
    expect(a.text).toContain('1011초로 올리세요');
  });

  it('경계값: 최악이 예산과 같으면 여유로 본다', () => {
    // 예산 = 600 - 150 = 450초. 4500 ÷ 10 = 450초
    const ok = adviseNumPredict({ rate: 10, predict: 4500, limit: 600 });
    expect(ok.level).toBe('ok');
    expect(ok.advised).toBe(4000);
    expect(ok.text).toContain('상한의 75%');

    const over = adviseNumPredict({ rate: 10, predict: 4510, limit: 600 });
    expect(over.level).toBe('warn');
  });

  it('경계값: 예비가 제한보다 크면 예산은 0 이고 권장도 0 이다', () => {
    const a = adviseNumPredict({ rate: 20, predict: 100, limit: 100 });
    expect(a.level).toBe('warn');
    expect(a.advised).toBe(0);
  });

  it('미측정이면 숫자를 지어내지 않는다', () => {
    const a = adviseNumPredict({ rate: 0, predict: 16000, limit: 600 });
    expect(a.level).toBe('unmeasured');
    expect(a.advised).toBeNull();
    expect(a.worstSeconds).toBeNull();
    expect(a.text).toContain('이 서버에서 재보기');
    expect(a.text).not.toMatch(/\d+초/);
  });

  it('시간 제한 미설정이면 최악 소요만 말하고 프록시 확인을 권한다', () => {
    const a = adviseNumPredict({ rate: 18.6, predict: 16000, limit: 0 });
    expect(a.level).toBe('unbounded');
    expect(a.advised).toBeNull();
    expect(a.text).toContain('최악 861초');
    expect(a.text).toContain('read timeout');
  });

  it('예비 시간을 바꾸면 예산이 따라 바뀐다', () => {
    const a = adviseNumPredict({ rate: 10, predict: 1000, limit: 600, reserve: 0 });
    expect(a.advised).toBe(6000);
  });
});
