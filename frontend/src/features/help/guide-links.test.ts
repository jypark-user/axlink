import { describe, expect, it } from 'vitest';
import { assetPathOf, routeOf, sectionsOf, splitAnchor } from '@/features/help/guide-links';

const FILES = new Map([
  ['요구사항-등록.md', 'requirement-baseline'],
  ['도구-연동-가이드.md', 'tool-integration'],
]);

describe('routeOf', () => {
  it('설명서 문서 링크는 설명서 주소로, 절은 그대로 붙인다', () => {
    expect(routeOf('요구사항-등록.md#spec-format', FILES)).toBe(
      '/guide/requirement-baseline#spec-format',
    );
    expect(routeOf('도구-연동-가이드.md', FILES)).toBe('/guide/tool-integration');
    // 마크다운이 한글 파일 이름을 인코딩해 넘겨도 같다
    expect(routeOf(encodeURI('요구사항-등록.md') + '#flow', FILES)).toBe(
      '/guide/requirement-baseline#flow',
    );
  });

  it('같은 문서 안 절은 그대로, 바깥 주소와 모르는 파일은 바깥 링크로 둔다', () => {
    expect(routeOf('#errors', FILES)).toBe('#errors');
    expect(routeOf('https://github.com/x', FILES)).toBeNull();
    expect(routeOf('배포-운영-절차.md', FILES)).toBeNull();
  });
});

describe('splitAnchor', () => {
  it('제목 끝의 {#id} 를 떼어 앵커로 쓴다', () => {
    expect(splitAnchor('3. 명세서 형식 {#spec-format}')).toEqual({
      id: 'spec-format',
      children: ['3. 명세서 형식'],
    });
    expect(splitAnchor('앵커 없는 제목')).toEqual({ children: '앵커 없는 제목' });
  });
});

describe('sectionsOf', () => {
  it('## 제목 중 앵커가 있는 것만 목차로 낸다', () => {
    const md = '## 1. 흐름 {#flow}\n### 3.1 읽는 형식 {#x}\n## 앵커 없음\n## **R** 규칙 {#rules}';
    expect(sectionsOf(md)).toEqual([
      { id: 'flow', title: '1. 흐름' },
      { id: 'rules', title: 'R 규칙' },
    ]);
  });
});

describe('assetPathOf', () => {
  it('문서의 images/ 상대 경로를 그림 API 경로로 바꾼다', () => {
    expect(assetPathOf('images/tool-integration/01-connections.png')).toBe(
      '/help/assets/images/tool-integration/01-connections.png',
    );
    expect(assetPathOf('./images/요구사항/a.png')).toBe(
      `/help/assets/images/${encodeURIComponent('요구사항')}/a.png`,
    );
  });

  it('바깥 주소나 images 밖 경로는 건드리지 않는다', () => {
    expect(assetPathOf('https://example.com/a.png')).toBeNull();
    expect(assetPathOf('data:image/png;base64,AAAA')).toBeNull();
    expect(assetPathOf('/ax-link/a.png')).toBeNull();
    expect(assetPathOf('other/a.png')).toBeNull();
  });
});
