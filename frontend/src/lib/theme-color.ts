import { useEffect, useState } from 'react';
import { useTheme } from '@/features/settings/theme-context';

/**
 * `var(--color-…)` 를 실제 색 문자열로 바꿔 준다.
 * SVG 로 그리는 라이브러리(gantt-task-react)는 CSS 변수를 받지 못해서 필요하다.
 * 테마가 바뀌면 다시 읽는다.
 */
const VAR_PATTERN = /^var\((--[^)]+)\)$/;

function readColor(color: string, styles: CSSStyleDeclaration): string {
  const match = VAR_PATTERN.exec(color.trim());
  if (!match) return color;
  return styles.getPropertyValue(match[1]).trim() || color;
}

export function useThemeColors(colors: string[]): string[] {
  const { resolved } = useTheme();
  const key = colors.join('\n');
  const [palette, setPalette] = useState<Record<string, string>>({});

  useEffect(() => {
    const read = () => {
      const styles = getComputedStyle(document.documentElement);
      const next: Record<string, string> = {};
      for (const color of key.split('\n')) next[color] = readColor(color, styles);
      setPalette(next);
    };
    read();
    // 테마 클래스가 붙은 다음 프레임에 한 번 더 — 첫 렌더에서 이전 색을 잡는 것을 막는다.
    const frame = requestAnimationFrame(read);
    return () => cancelAnimationFrame(frame);
  }, [key, resolved]);

  return colors.map((color) => palette[color] ?? color);
}

export function useThemeColor(color: string): string {
  return useThemeColors([color])[0];
}
