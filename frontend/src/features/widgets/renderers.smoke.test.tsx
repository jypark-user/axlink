import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CHAT_TEMPLATES, sampleInfographic } from '@/features/ax-query/viz-preview';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import type { WidgetSpec } from '@/types/api';

/**
 * 그림마다 한 번씩 실제로 그려 본다.
 * 렌더러는 행 모양을 손으로 다루는 코드가 많아(피벗·누적·정렬) 축 키가 어긋나거나 값이 비면
 * 화면에서야 터진다. 표본으로라도 한 번 그려 두면 그 부류는 여기서 걸린다.
 */
describe('widget renderers', () => {
  it.each(CHAT_TEMPLATES)('%s 는 표본 값으로 그려진다', (template) => {
    const infographic = sampleInfographic(template);
    const Renderer = resolveWidgetRenderer(template);
    const spec = {
      template,
      title: infographic.title,
      query: null,
      options: null,
    } as unknown as WidgetSpec;

    const { container } = render(<Renderer spec={spec} data={infographic.data} />);

    expect(container.firstChild).not.toBeNull();
  });
});
