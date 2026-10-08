import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/common/toaster';
import { DataState } from '@/components/common/data-state';
import { adviseNumPredict, DEFAULT_RESERVE_SECONDS } from '@/features/settings/llm-advice';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type {
  EmbeddingStatusResponse,
  LlmMeasureResponse,
  LlmModelListResponse,
  LlmModelResponse,
  LlmSettingResponse,
} from '@/types/api';

const FIELD = 'flex flex-col gap-1.5';
const HINT = 'text-muted-foreground text-xs leading-relaxed';
const DEBOUNCE_MS = 500;

const ctxText = (m: LlmModelResponse | null): string =>
  m === null || m.numCtx === null ? '' : String(m.numCtx);

/** 목록에 붙이는 용도 표시. 이름으로 짐작하지 않고 서버가 알려준 용도만 쓴다. */
const PURPOSE_TAG: Record<LlmModelResponse['purpose'], string> = {
  ANSWER: '',
  EMBEDDING: ' · 검색 전용(고를 수 없음)',
  UNKNOWN: ' · 용도 확인 필요',
};

/** 답변 모델로 처음 고를 것. 검색 전용은 건너뛴다. */
const firstAnswerModel = (list: LlmModelResponse[]): LlmModelResponse | undefined =>
  list.find((m) => m.purpose === 'ANSWER') ?? list.find((m) => m.purpose !== 'EMBEDDING');

/**
 * AI 모델 설정 (ARC-011 · ARC-022). 플랫폼 관리자만 연다.
 *
 * 답변 모델과 검색 모델을 나눠 보인다. 답변 모델은 서버 주소를 치는 동안 목록을 받아오고,
 * 모델을 고르면 그 모델에 저장된 문맥 길이·생성 토큰을 불러온다. 검색 모델은 색인과 묶여
 * 있어 여기서 바꾸지 않고 현황만 보인다.
 */
export function LlmSettingsSection(): ReactNode {
  const state = useAsync<LlmSettingResponse>(() => api.get<LlmSettingResponse>('/ai/settings'), []);
  return (
    <div className="flex flex-col gap-2">
      <SectionTitle title="답변 모델" hint="질문을 해석하고 답과 문서 초안을 쓰는 모델입니다." />
      <DataState state={state} onRetry={state.reload}>
        {(setting) => (
          <LlmSettingsForm
            key={setting.updatedAt ?? 'init'}
            setting={setting}
            onSaved={state.reload}
          />
        )}
      </DataState>
      <Separator className="my-2" />
      <SectionTitle
        title="검색 모델"
        hint="문서를 벡터로 바꿔 색인하고, 질문과 비슷한 문서를 찾는 모델(임베딩)입니다."
      />
      <EmbeddingStatusPanel />
    </div>
  );
}

function SectionTitle({ title, hint }: { title: string; hint: string }): ReactNode {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className={HINT}>{hint}</p>
    </div>
  );
}

function EmbeddingStatusPanel(): ReactNode {
  const state = useAsync<EmbeddingStatusResponse>(
    () => api.get<EmbeddingStatusResponse>('/ai/embedding'),
    [],
  );
  return (
    <DataState state={state} onRetry={state.reload}>
      {(e) => (
        <div className="flex flex-col gap-2 py-2 text-sm">
          <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted-foreground">적용 모델</dt>
            <dd className="font-mono">{e.model}</dd>
            <dt className="text-muted-foreground">서버</dt>
            <dd className="font-mono break-all">
              {e.provider === 'fake' ? '가짜 구현체(시험용)' : e.baseUrl}
              {e.serverHasModel === false && (
                <span className="text-destructive"> · 서버 목록에 없음</span>
              )}
              {e.serverHasModel === null && e.provider !== 'fake' && (
                <span className="text-muted-foreground"> · 서버 확인 못 함</span>
              )}
            </dd>
            <dt className="text-muted-foreground">차원</dt>
            <dd>
              {e.dimension}
              {e.columnDimension !== null && e.columnDimension !== e.dimension
                ? ` (색인 칸은 ${e.columnDimension}, 맞지 않음)`
                : ''}
            </dd>
            <dt className="text-muted-foreground">정한 곳</dt>
            <dd>환경변수 AXLINK_EMBEDDING_MODEL</dd>
            <dt className="text-muted-foreground">색인 모델</dt>
            <dd>
              {e.indexModels.length === 0
                ? '색인된 문서가 없습니다.'
                : e.indexModels
                    .map((m) => `${m.model} ${m.chunks.toLocaleString('ko-KR')}조각`)
                    .join(', ')}
            </dd>
          </dl>
          {e.consistent ? (
            <p className="rounded bg-emerald-500/10 p-2 text-xs text-emerald-700 dark:text-emerald-300">
              색인이 모두 지금 검색 모델로 만들어졌습니다. 문서 검색과 색인이 정상입니다.
            </p>
          ) : (
            <p className="rounded bg-destructive/10 p-2 text-xs text-destructive">{e.message}</p>
          )}
          <p className={HINT}>{e.changeBlockedReason}</p>
        </div>
      )}
    </DataState>
  );
}

function LlmSettingsForm({
  setting,
  onSaved,
}: {
  setting: LlmSettingResponse;
  onSaved: () => void;
}): ReactNode {
  const { toast } = useToast();
  const initial = setting.models.find((m) => m.name === setting.model) ?? null;
  const [baseUrl, setBaseUrl] = useState(setting.baseUrl);
  const [models, setModels] = useState<LlmModelResponse[]>(setting.models);
  const [modelName, setModelName] = useState(initial?.name ?? '');
  const [listStatus, setListStatus] = useState<string | null>(null);
  const [listing, setListing] = useState(false);
  const [numCtx, setNumCtx] = useState<string>(ctxText(initial));
  const [numPredict, setNumPredict] = useState<string>(String(initial?.numPredict ?? 16000));
  const [measuring, setMeasuring] = useState(false);
  const [saving, setSaving] = useState(false);
  const firstRender = useRef(true);

  const selected = useMemo(
    () => models.find((m) => m.name === modelName) ?? null,
    [models, modelName],
  );

  // 모델을 고르면 그 모델에 저장된 값을 불러온다. 문맥은 최대치가 기본이다.
  const pickModel = (name: string, list: LlmModelResponse[] = models) => {
    setModelName(name);
    const m = list.find((x) => x.name === name);
    if (m) {
      setNumCtx(ctxText(m));
      setNumPredict(String(m.numPredict));
    }
  };

  const refreshModels = async (url: string, currentModel: string) => {
    setListing(true);
    try {
      const res = await api.post<LlmModelListResponse>(
        `/ai/models/refresh?baseUrl=${encodeURIComponent(url)}`,
      );
      setModels(res.models);
      if (res.error) {
        setListStatus(res.error);
      } else if (res.models.length === 0) {
        setListStatus('서버에 올라온 모델이 없습니다. 서버에 모델을 먼저 올려 두세요.');
      } else {
        setListStatus(`모델 ${res.models.length}개를 받아왔습니다.`);
      }
      const keep =
        res.models.find((m) => m.name === currentModel && m.purpose !== 'EMBEDDING') ??
        firstAnswerModel(res.models);
      setModelName(keep?.name ?? '');
      if (keep) {
        setNumCtx(ctxText(keep));
        setNumPredict(String(keep.numPredict));
      }
    } catch (e) {
      setListStatus(isApiError(e) ? e.message : '목록을 받아오지 못했습니다.');
    } finally {
      setListing(false);
    }
  };

  // 주소를 치는 동안 목록을 받아온다. 실패는 상태 문구다. 대화상자를 띄우지 않는다.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const trimmed = baseUrl.trim();
    const timer = window.setTimeout(() => {
      if (!trimmed) {
        setModels([]);
        setListStatus('서버 주소를 입력하세요.');
        return;
      }
      void refreshModels(trimmed, modelName);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
    // 주소가 바뀔 때만 다시 조회한다. 모델 이름은 그 시점 값을 읽으면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl]);

  const measure = async () => {
    if (!selected) return;
    setMeasuring(true);
    try {
      const res = await api.post<LlmMeasureResponse>(
        `/ai/models/measure?baseUrl=${encodeURIComponent(baseUrl.trim())}&model=${encodeURIComponent(selected.name)}`,
      );
      // 폼 필드에만 쓰면 화면이 안 바뀌던 사고가 있었다. 알림으로 돌려주고 캐시를 다시 읽는다.
      toast({
        title: `${res.model} · ${res.tokPerSec.toFixed(1)} tok/s`,
        description: `${res.evalCount}토큰을 ${res.evalDurationSeconds.toFixed(2)}초에 생성했습니다. 적재 시간은 뺀 순수 생성 속도입니다.`,
        variant: 'success',
      });
      setModels((prev) =>
        prev.map((m) =>
          m.name === res.model && m.baseUrl === selected.baseUrl
            ? { ...m, tokPerSec: res.tokPerSec, measuredAt: res.measuredAt }
            : m,
        ),
      );
    } catch (e) {
      toast({
        title: '생성 속도를 재지 못했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setMeasuring(false);
    }
  };

  const save = async () => {
    if (!selected) return;
    const predict = Number(numPredict);
    if (!Number.isInteger(predict) || predict <= 0) {
      toast({ title: '생성 토큰은 1 이상의 정수여야 합니다.', variant: 'error' });
      return;
    }
    const ctx = numCtx.trim() === '' ? null : Number(numCtx);
    if (ctx !== null && (!Number.isInteger(ctx) || ctx <= 0)) {
      toast({ title: '컨텍스트 길이는 비우거나 1 이상의 정수여야 합니다.', variant: 'error' });
      return;
    }
    setSaving(true);
    try {
      await api.put<LlmSettingResponse>('/ai/settings', {
        baseUrl: baseUrl.trim(),
        model: selected.name,
        numCtx: ctx,
        numPredict: predict,
      });
      toast({ title: 'AI 모델 설정을 저장했습니다.', variant: 'success' });
      onSaved();
    } catch (e) {
      toast({
        title: '저장에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  const advice = adviseNumPredict({
    rate: selected?.tokPerSec ?? 0,
    predict: Number(numPredict) || 0,
    limit: setting.requestTimeoutSeconds,
  });

  const embeddingOnly = selected?.purpose === 'EMBEDDING';

  return (
    <div className="flex flex-col gap-5 py-3">
      <p className={HINT}>
        지금 적용: <span className="font-mono text-foreground">{setting.model}</span> (
        {setting.source === 'DB' ? '저장된 설정' : '저장한 적 없음, 환경변수 기본값'}).{' '}
        {setting.usedFor.join('·')}에 같은 모델을 씁니다.
      </p>
      {setting.provider !== 'ollama' && (
        <p className="rounded bg-muted p-2 text-xs">
          지금은 <code className="font-mono">{setting.provider}</code> 구현체로 돌고 있어 이 설정이
          쓰이지 않습니다. 환경변수 AXLINK_LLM_PROVIDER 를 ollama 로 두면 적용됩니다.
        </p>
      )}

      <div className={FIELD}>
        <Label htmlFor="llm-base-url">LLM 서버 주소</Label>
        <div className="flex gap-2">
          <Input
            id="llm-base-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:11434"
            autoComplete="off"
          />
          <Button
            type="button"
            variant="outline"
            disabled={listing || !baseUrl.trim()}
            onClick={() => void refreshModels(baseUrl.trim(), modelName)}
          >
            {listing ? '조회 중…' : '새로 고침'}
          </Button>
        </div>
        <p className={HINT}>
          {listStatus ??
            (models.length > 0
              ? `저장된 목록 ${models.length}개 · ${models[0] ? formatDateTime(models[0].fetchedAt) : ''} 기준`
              : '온프레미스 LLM 서버 주소입니다. 입력하면 그 서버에 올라온 모델 목록을 받아옵니다.')}
        </p>
      </div>

      <div className={FIELD}>
        <Label htmlFor="llm-model">모델</Label>
        <Select value={modelName} onValueChange={pickModel} disabled={models.length === 0}>
          <SelectTrigger id="llm-model">
            <SelectValue placeholder="모델을 고르세요" />
          </SelectTrigger>
          <SelectContent>
            {models.map((m) => (
              <SelectItem key={m.name} value={m.name} disabled={m.purpose === 'EMBEDDING'}>
                {m.name}
                {m.parameterSize ? ` · ${m.parameterSize}` : ''}
                {m.quantization ? ` · ${m.quantization}` : ''}
                {PURPOSE_TAG[m.purpose]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selected && (
          <p className={HINT}>
            최대 문맥{' '}
            {selected.contextLength > 0
              ? selected.contextLength.toLocaleString('ko-KR')
              : '알 수 없음'}
            {' · '}도구 호출 {selected.supportsTools ? '지원' : '미지원'}
            {selected.tokPerSec !== null && selected.measuredAt
              ? ` · 실측 ${selected.tokPerSec.toFixed(1)} tok/s (${formatDateTime(selected.measuredAt)})`
              : ' · 생성 속도 미측정'}
          </p>
        )}
        {embeddingOnly && (
          <p className="rounded bg-destructive/10 p-2 text-xs text-destructive">
            서버가 이 모델을 검색(임베딩) 전용으로 알려 왔습니다. 답변 모델로 저장할 수 없습니다.
          </p>
        )}
        {selected?.purpose === 'UNKNOWN' && (
          <p className="rounded bg-muted p-2 text-xs">
            서버가 이 모델의 용도를 알려 주지 않았습니다(확인 필요). 저장할 때 짧은 생성을 해 보고,
            되면 저장합니다.
            {selected.verifiedAt ? ` 마지막 확인 ${formatDateTime(selected.verifiedAt)}.` : ''}
          </p>
        )}
        {selected && !embeddingOnly && !selected.supportsTools && (
          <p className="rounded bg-destructive/10 p-2 text-xs text-destructive">
            ⚠ 이 모델은 도구 호출을 지원하지 않습니다. 에이전트가 도구 호출로 동작한다면 이 모델로는
            동작하지 않습니다. AX Link 의 질의·초안·위젯 선택은 도구 호출을 쓰지 않아 지금 기능에는
            영향이 없습니다.
          </p>
        )}
      </div>

      <Separator />

      <div className={FIELD}>
        <Label htmlFor="llm-num-ctx">컨텍스트 길이 (num_ctx)</Label>
        <Input
          id="llm-num-ctx"
          inputMode="numeric"
          value={numCtx}
          onChange={(e) => setNumCtx(e.target.value.replace(/[^\d]/g, ''))}
          placeholder="비우면 모델 기본값"
          disabled={!selected}
        />
        <p className={HINT}>
          {selected && selected.contextLength > 0
            ? `이 모델의 최대치는 ${selected.contextLength.toLocaleString('ko-KR')} 토큰이고 그 값을 그대로 채웠습니다. 긴 문서와 코드를 한 번에 담아야 앞부분이 조용히 잘리지 않습니다. `
            : '서버가 최대치를 알려주지 않아 비워 두었습니다. 비우면 모델 기본값을 씁니다. '}
          서버는 이 길이만큼 KV 캐시를 미리 잡습니다. 메모리가 부족해 모델 적재가 실패하면 값을
          낮추세요.
        </p>
      </div>

      <div className={FIELD}>
        <Label htmlFor="llm-num-predict">한 턴 최대 생성 토큰 (num_predict)</Label>
        <div className="flex gap-2">
          <Input
            id="llm-num-predict"
            inputMode="numeric"
            value={numPredict}
            onChange={(e) => setNumPredict(e.target.value.replace(/[^\d]/g, ''))}
            disabled={!selected}
          />
          <Button
            type="button"
            variant="outline"
            disabled={!selected || measuring}
            onClick={() => void measure()}
            title="짧은 프롬프트를 보내 순수 생성 속도를 잽니다. 적재 안 된 모델은 수십 초가 걸립니다."
          >
            {measuring ? '재는 중…' : '이 서버에서 재보기'}
          </Button>
        </div>
        <p
          className={cn(
            'rounded p-2 text-xs leading-relaxed',
            advice.level === 'warn'
              ? 'bg-destructive/10 text-destructive'
              : advice.level === 'ok'
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                : 'bg-muted text-muted-foreground',
          )}
        >
          {advice.text}
        </p>
        <p className={HINT}>
          값 ÷ 생성 속도 = 최악 소요 시간입니다. 이것이 요청 시간 제한
          {setting.requestTimeoutSeconds > 0
            ? `(지금 ${Math.ceil(setting.requestTimeoutSeconds)}초, AXLINK_LLM_TIMEOUT)`
            : '(미설정)'}
          과 프록시 read timeout 을 넘으면 504 로 끊깁니다. 권장값은 제한에서 예비{' '}
          {DEFAULT_RESERVE_SECONDS}초(접두 캐시가 깨졌을 때의 프리필 몫)를 뺀 시간에 속도를 곱해 천
          단위로 내린 값입니다.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <span className={HINT}>
          {setting.updatedAt
            ? `마지막 저장 ${formatDateTime(setting.updatedAt)}`
            : '아직 저장한 적이 없습니다. 환경변수 기본값으로 돕니다.'}
          {' · '}저장 전에 그 모델로 짧은 생성을 해 보고, 안 되면 저장하지 않습니다.
        </span>
        <Button
          type="button"
          disabled={!selected || embeddingOnly || saving}
          onClick={() => void save()}
        >
          {saving ? '확인·저장 중…' : '저장'}
        </Button>
      </div>
    </div>
  );
}
