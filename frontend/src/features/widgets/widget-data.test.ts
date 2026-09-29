import { describe, expect, it } from 'vitest';

const withLabelColumn = {
  columns: [
    { key: 'd0', label: '용역사', type: 'string' },
    { key: 'd0_label', label: '용역사 명', type: 'string' },
    { key: 'value', label: '이슈 건수', type: 'number' },
  ],
  rows: [],
} as unknown as WidgetDataResponse;

describe('resolveColumns', () => {
  it('이름 열이 있는 차원의 식별자 열은 기본으로 숨긴다', () => {
    expect(resolveColumns(withLabelColumn, null).map((c) => c.key)).toEqual(['d0_label', 'value']);
  });

  it('열을 고르면 그 순서대로 보이고 식별자 열도 고를 수 있다', () => {
    const picked = resolveColumns(withLabelColumn, {
      unit: null,
      sort: null,
      threshold: null,
      stacked: null,
      showLegend: null,
      compareWithPrevious: null,
      columns: ['value', 'd0'],
    });
    expect(picked.map((c) => c.key)).toEqual(['value', 'd0']);
  });
});
import { categoryKey, resolveColumns } from '@/features/widgets/widget-data';
import type { WidgetDataResponse } from '@/types/api';

/**
 * 축 키가 행에 없으면 recharts 는 오류 대신 인덱스(0,1,2…)를 그린다.
 * 조용히 틀리는 종류라 실제 응답 모양 그대로 굳혀둔다.
 */
const data = (
  columns: { key: string; label: string; type: string }[],
  dimensions: string[] = [],
): WidgetDataResponse =>
  ({
    measure: 'm',
    measureLabel: '지표',
    unit: '건',
    dimensions,
    columns,
    rows: [],
    total: null,
    previousTotal: null,
    appliedProjectIds: [],
    truncated: false,
    generatedAt: '2026-01-01T00:00:00Z',
  }) as unknown as WidgetDataResponse;

describe('categoryKey', () => {
  it('행의 실제 키(d0)를 고른다 — 카탈로그 식별자가 아니다', () => {
    // dimensions 는 'issue_severity' 지만 행 키는 'd0' 이다.
    expect(
      categoryKey(
        data(
          [
            { key: 'd0', label: '이슈 심각도', type: 'string' },
            { key: 'value', label: '열린 이슈 수', type: 'number' },
          ],
          ['issue_severity'],
        ),
      ),
    ).toBe('d0');
  });

  it('사람이 읽는 이름 컬럼이 있으면 그쪽을 고른다', () => {
    // 프로젝트 차원은 d0 가 UUID 라 축에 쓰면 UUID 가 그려진다.
    expect(
      categoryKey(
        data(
          [
            { key: 'd0', label: '프로젝트', type: 'string' },
            { key: 'd0_label', label: '프로젝트 명', type: 'string' },
            { key: 'value', label: '요구사항 이행률', type: 'number' },
          ],
          ['project'],
        ),
      ),
    ).toBe('d0_label');
  });

  it('숫자 컬럼은 범주 축으로 고르지 않는다', () => {
    expect(categoryKey(data([{ key: 'value', label: '값', type: 'number' }]))).toBe('value');
  });

  it('컬럼이 없으면 null 이다', () => {
    expect(categoryKey(data([]))).toBeNull();
  });
});
