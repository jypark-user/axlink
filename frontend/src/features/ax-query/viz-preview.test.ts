import { describe, expect, it } from 'vitest';
import { CHAT_TEMPLATES, sampleInfographic } from '@/features/ax-query/viz-preview';
import { widgetRenderers } from '@/features/widgets/renderer-registry';

describe('viz-preview', () => {
  it('채팅에 나오는 18종을 다룬다', () => {
    expect(CHAT_TEMPLATES).toHaveLength(18);
    expect(CHAT_TEMPLATES).not.toContain('STAT_CARD');
  });

  it('18종 모두 렌더러가 있고 그릴 값이 들어 있다', () => {
    for (const template of CHAT_TEMPLATES) {
      expect(widgetRenderers[template]).toBeTypeOf('function');
      const { data } = sampleInfographic(template);
      expect(data.rows.length).toBeGreaterThan(1);
      // 축으로 쓰는 키가 행에 실제로 있어야 한다 — 없으면 차트가 조용히 0,1,2 를 그린다.
      for (const dim of data.dimensions) {
        expect(data.rows[0].values).toHaveProperty(dim);
      }
      expect(data.columns.some((c) => c.type === 'number')).toBe(true);
    }
  });

  it('두 축이 필요한 그림은 축을 두 개 준다', () => {
    for (const template of ['STACKED_BAR_CHART', 'HEATMAP'] as const) {
      expect(sampleInfographic(template).data.dimensions).toHaveLength(2);
    }
  });
});
