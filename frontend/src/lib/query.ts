export type QueryParams = Record<string, unknown>;

/** 쿼리 값 하나를 문자열로. 객체를 그냥 String() 하면 '[object Object]' 가 서버로 간다. */
const asParam = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return JSON.stringify(value) ?? '';
};

export const toQueryString = (params?: QueryParams): string => {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      for (const v of value) sp.append(key, asParam(v));
    } else {
      sp.set(key, asParam(value));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
};
