import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type ThemeMode = 'light' | 'dark' | 'system';

export const themeModeLabel: Record<ThemeMode, string> = {
  light: '밝게',
  dark: '어둡게',
  system: '시스템 설정',
};

const STORAGE_KEY = 'ax-link.theme';

function readMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system';
  } catch {
    return 'system';
  }
}

function darkMediaQuery(): MediaQueryList | null {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;
}

const prefersDark = () => darkMediaQuery()?.matches ?? false;

interface ThemeValue {
  mode: ThemeMode;
  resolved: 'light' | 'dark';
  setMode: (mode: ThemeMode) => void;
}

const ThemeCtx = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [systemDark, setSystemDark] = useState(prefersDark);

  useEffect(() => {
    const media = darkMediaQuery();
    if (!media) return;
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const resolved: 'light' | 'dark' = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', resolved === 'dark');
    root.classList.toggle('light', mode === 'light');
    root.style.colorScheme = resolved;
  }, [mode, resolved]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      return;
    }
  }, []);

  const value = useMemo<ThemeValue>(() => ({ mode, resolved, setMode }), [mode, resolved, setMode]);

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeCtx);
  if (!value) {
    throw new Error('useTheme 는 ThemeProvider 안에서만 쓸 수 있습니다.');
  }
  return value;
}
