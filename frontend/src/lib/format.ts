const dateFmt = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
const dateTimeFmt = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});
const numberFmt = new Intl.NumberFormat('ko-KR');

const toDate = (v: string | number | Date): Date => (v instanceof Date ? v : new Date(v));

export const formatDate = (v: string | number | Date): string => dateFmt.format(toDate(v));

export const formatDateTime = (v: string | number | Date): string => dateTimeFmt.format(toDate(v));

export const formatRelative = (v: string | number | Date): string => {
  const d = toDate(v).getTime();
  const diff = Date.now() - d;
  const sec = Math.round(diff / 1000);
  if (Math.abs(sec) < 60) return '방금 전';
  const min = Math.round(sec / 60);
  if (Math.abs(min) < 60) return `${min}분 전`;
  const hr = Math.round(min / 60);
  if (Math.abs(hr) < 24) return `${hr}시간 전`;
  const day = Math.round(hr / 24);
  if (Math.abs(day) < 30) return `${day}일 전`;
  return formatDate(v);
};

export const formatNumber = (v: number): string => numberFmt.format(v);

export const formatPercent = (v: number, digits = 0): string => `${(v * 100).toFixed(digits)}%`;

export const formatBytes = (v: number): string => {
  if (v < 1024) return `${v} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let u = -1;
  let n = v;
  do {
    n /= 1024;
    u++;
  } while (n >= 1024 && u < units.length - 1);
  return `${n.toFixed(1)} ${units[u]}`;
};

export const formatPeriod = (start: string, end: string): string =>
  `${formatDate(start)} ~ ${formatDate(end)}`;
