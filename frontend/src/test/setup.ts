import '@testing-library/jest-dom/vitest';

/**
 * jsdom 에는 ResizeObserver 가 없다 — recharts 의 ResponsiveContainer 가 이걸 붙잡고 그린다.
 * 크기를 재려는 것이 아니라 그려지는지를 보려는 것이라, 아무 일도 하지 않는 것으로 충분하다.
 */
if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
}
