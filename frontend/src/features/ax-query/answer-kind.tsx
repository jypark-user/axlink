import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/http';
import { useAsync } from '@/lib/use-async';
import type { AiRuntimeResponse, SuggestionItem } from '@/types/api';

/** 답의 종류. 막힌 이유를 한 문구로 뭉치지 않는다. 조회 오류는 값 없음과 다르게 보인다. */
const KIND_LABEL: Record<string, string> = {
  PARTIAL: '일부만 답함',
  NUMBER_GUARD: '근거 없는 수치 문장 숨김',
  CLARIFY: '되묻기',
  NO_DATA: '값 없음',
  NO_DOCUMENTS: '문서 없음',
  NO_RELEVANT_DOCUMENTS: '맞는 근거 없음',
  UNSUPPORTED: '지원하지 않는 질문',
  QUERY_ERROR: '조회 오류',
  OFF_TOPIC: '사업 밖 질문',
};

export function answerKindLabel(reason: string | null | undefined): string | null {
  return reason ? (KIND_LABEL[reason] ?? null) : null;
}

/** 답 아래 이어 물을 질문. 되묻기면 고를 것이다. 서버가 낸 것만, 최대 셋. */
export function SuggestionChips({
  items,
  clarify,
  onSelect,
  disabled,
}: {
  items: SuggestionItem[];
  clarify: boolean;
  onSelect: (item: SuggestionItem) => void;
  disabled?: boolean;
}): ReactNode {
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-muted-foreground text-xs mb-1.5">
        {clarify ? '보려는 것을 골라 주십시오' : '이어서 물어보기'}
      </p>
      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.hint}>
            <Button
              type="button"
              variant="outline"
              disabled={disabled}
              onClick={() => onSelect(item)}
              className="text-sm text-muted-foreground hover:text-primary h-auto rounded-full px-3.5 py-[7px] font-normal whitespace-normal"
            >
              {item.question}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 지금 어떤 모델이 답하는지. 고정 응답이면 실제 모델 답이 아님을 분명히 알린다. */
export function ModelBadge(): ReactNode {
  const runtime = useAsync<AiRuntimeResponse>(() => api.get<AiRuntimeResponse>('/ai/runtime'), []);
  const data = runtime.data;
  if (runtime.error) {
    return (
      <p className="text-muted-foreground text-[11px] mt-2 text-center">답변 모델 확인 실패</p>
    );
  }
  if (!data) return null;
  const code = data.codeVersion ? ` · 코드 ${data.codeVersion}` : '';
  if (data.fixed) {
    return (
      <p className="text-destructive text-[11px] mt-2 text-center font-semibold">
        고정 응답(시험용) 모드입니다. 실제 모델의 답이 아닙니다.{code}
      </p>
    );
  }
  return (
    <p className="text-muted-foreground text-[11px] mt-2 text-center">
      답변 모델 {data.model ?? data.llmProvider}
      {code}
    </p>
  );
}
