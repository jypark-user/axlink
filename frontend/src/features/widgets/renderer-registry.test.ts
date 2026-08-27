import { describe, expect, it } from 'vitest';
import { resolveWidgetRenderer, widgetRenderers } from '@/features/widgets/renderer-registry';
import { UnsupportedWidget } from '@/features/widgets/renderers';
import type { WidgetTemplate } from '@/types/api';

const TEMPLATES: WidgetTemplate[] = [
  'STAT_CARD',
  'BAR_CHART',
  'LINE_CHART',
  'PIE_CHART',
  'PROGRESS_LIST',
  'DATA_TABLE',
  'CHECKLIST',
  'GANTT_SUMMARY',
  'STATUS_FLOW',
  'HEATMAP',
  'AREA_CHART',
  'STACKED_BAR_CHART',
  'HORIZONTAL_BAR_CHART',
  'DONUT_CHART',
  'RADAR_CHART',
  'CUMULATIVE_FLOW',
  'PARETO',
  'TREEMAP',
  'SLOPE_CHART',
  'BUMP_CHART',
  'SPARKLINE',
  'BULLET_CHART',
  'CALENDAR_HEATMAP',
];

describe('renderer-registry', () => {
  it('has exactly the 23 CONSTANT_CASE template keys', () => {
    expect(Object.keys(widgetRenderers).sort()).toEqual([...TEMPLATES].sort());
  });

  it('resolves every template to its own renderer, never the fallback', () => {
    for (const template of TEMPLATES) {
      const renderer = resolveWidgetRenderer(template);
      expect(renderer).toBe(widgetRenderers[template]);
      expect(renderer).not.toBe(UnsupportedWidget);
    }
  });

  it('does not resolve lowercase or unknown templates', () => {
    expect(resolveWidgetRenderer('stat-card')).toBe(UnsupportedWidget);
    expect(resolveWidgetRenderer('sunburst')).toBe(UnsupportedWidget);
  });
});
