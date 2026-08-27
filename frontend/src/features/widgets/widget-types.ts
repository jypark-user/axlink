import type { ReactElement } from 'react';
import type { ApiError } from '@/lib/api-error';
import type { WidgetDataResponse, WidgetSpec } from '@/types/api';

export interface WidgetRendererProps {
  spec: WidgetSpec;
  data: WidgetDataResponse;
}

export type WidgetRenderer = (props: WidgetRendererProps) => ReactElement;

export type WidgetViewState =
  | { kind: 'loading' }
  | { kind: 'error'; error: ApiError }
  | { kind: 'empty' }
  | { kind: 'ready'; data: WidgetDataResponse };
