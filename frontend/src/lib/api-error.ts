import type { ErrorResponse, FieldError } from '@/types/api';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly path: string;
  readonly timestamp: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    path = '',
    timestamp = '',
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.path = path;
    this.timestamp = timestamp;
  }

  static from(status: number, payload: unknown): ApiError {
    const err = (payload ?? {}) as Partial<ErrorResponse>;
    return new ApiError(
      status,
      err.code ?? 'INTERNAL',
      err.message ?? '요청 처리 중 오류가 발생했습니다.',
      err.details ?? {},
      err.path ?? '',
      err.timestamp ?? '',
    );
  }
}

export const isApiError = (e: unknown): e is ApiError => e instanceof ApiError;

export const toFieldErrors = (e: unknown): FieldError[] => {
  if (!isApiError(e)) return [];
  const raw = e.details?.fieldErrors;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (f): f is FieldError =>
      !!f &&
      typeof (f as FieldError).field === 'string' &&
      typeof (f as FieldError).reason === 'string',
  );
};

export const fieldErrorMap = (e: unknown): Record<string, string> => {
  const map: Record<string, string> = {};
  for (const fe of toFieldErrors(e)) map[fe.field] = fe.reason;
  return map;
};
