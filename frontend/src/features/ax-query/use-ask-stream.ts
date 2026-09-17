import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/lib/api-error';
import { openStream } from '@/lib/http';
import { parseSseStream } from '@/lib/sse';
import { registerVizPreview } from '@/features/ax-query/viz-preview';
import type {
  AskRequest,
  MessageSourceResponse,
  QueryRouting,
  SseDeltaEvent,
  SseDoneEvent,
  SseInfographicEvent,
  SseSourcesEvent,
  SseStartEvent,
} from '@/types/api';

export type AskPhase = 'idle' | 'streaming' | 'finalizing' | 'aborted' | 'error';

export interface AskStreamState {
  phase: AskPhase;
  routing: QueryRouting | null;
  draftText: string;
  sources: MessageSourceResponse[];
  infographics: SseInfographicEvent[];
  /** done 이벤트가 알려준 소요 시간(ms) */
  elapsedMs: number | null;
  /** 지금 답을 받고 있는 대화. 다른 대화를 열면 이 값이 달라 그쪽엔 그리지 않는다 */
  conversationId: string | null;
  assistantMessageId: string | null;
  error: ApiError | null;
  ask: (conversationId: string, request: AskRequest) => Promise<void>;
  abort: () => void;
  reset: () => void;
}

/** 디버깅용 — 서버가 보낸 SSE 원문을 개발 빌드에서만 찍는다. */
const debugLog = (name: string, raw: string): void => {
  if (!import.meta.env.DEV) return;

  console.log(`%c[ask:${name}]`, 'color:#6b7fd7;font-weight:bold', raw);
};

const parse = <T>(raw: string): T | null => {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
};

export function useAskStream(onSettled: (conversationId: string) => void): AskStreamState {
  const [phase, setPhase] = useState<AskPhase>('idle');
  const [routing, setRouting] = useState<QueryRouting | null>(null);
  const [draftText, setDraftText] = useState('');
  const [sources, setSources] = useState<MessageSourceResponse[]>([]);
  const [infographics, setInfographics] = useState<SseInfographicEvent[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [assistantMessageId, setAssistantMessageId] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const phaseRef = useRef<AskPhase>('idle');

  phaseRef.current = phase;

  const reset = useCallback(() => {
    setPhase('idle');
    setRouting(null);
    setDraftText('');
    setSources([]);
    setInfographics([]);
    setElapsedMs(null);
    setActiveConversationId(null);
    setAssistantMessageId(null);
    setError(null);
  }, []);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  useEffect(() => () => controllerRef.current?.abort(), []);

  // 개발 빌드에서만 — 콘솔의 axViz() 로 그림 10종을 채팅 화면에서 바로 넘겨 본다.
  useEffect(() => registerVizPreview((e) => setInfographics(e ? [e] : [])), []);

  const ask = useCallback(
    async (conversationId: string, request: AskRequest) => {
      if (phaseRef.current === 'streaming') return;
      const controller = new AbortController();
      controllerRef.current = controller;
      setPhase('streaming');
      setActiveConversationId(conversationId);
      setDraftText('');
      setSources([]);
      setInfographics([]);
      setElapsedMs(null);
      setRouting(null);
      setError(null);
      setAssistantMessageId(null);
      try {
        const res = await openStream(
          `/conversations/${conversationId}/messages`,
          request,
          controller.signal,
        );
        for await (const event of parseSseStream(res.body!, controller.signal)) {
          if (event.event === 'start') {
            const payload = parse<SseStartEvent>(event.data);
            debugLog('routing', event.data);
            if (payload) {
              setRouting(payload.routing);
              setAssistantMessageId(payload.assistantMessageId);
            }
          } else if (event.event === 'delta') {
            const payload = parse<SseDeltaEvent>(event.data);
            if (payload) setDraftText((prev) => prev + payload.text);
          } else if (event.event === 'sources') {
            const payload = parse<SseSourcesEvent>(event.data);
            if (payload) setSources(payload.sources);
          } else if (event.event === 'infographic') {
            debugLog('infographic', event.data);
            const payload = parse<SseInfographicEvent>(event.data);
            // 그림은 여러 장 올 수 있다. 같은 자리가 다시 오면 덮어쓴다.
            if (payload)
              setInfographics((prev) => [...prev.filter((b) => b.slot !== payload.slot), payload]);
          } else if (event.event === 'done') {
            const done = parse<SseDoneEvent>(event.data);
            if (done) setElapsedMs(done.elapsedMs);
            setPhase('finalizing');
            onSettled(conversationId);
            return;
          } else if (event.event === 'error') {
            setError(ApiError.from(500, parse(event.data)));
            setPhase('error');
            return;
          }
        }
        if (controller.signal.aborted) {
          setPhase('aborted');
        } else {
          setPhase('finalizing');
          onSettled(conversationId);
        }
      } catch (e) {
        if (controller.signal.aborted) {
          setPhase('aborted');
          return;
        }
        setError(e instanceof ApiError ? e : ApiError.from(0, null));
        setPhase('error');
      } finally {
        controllerRef.current = null;
      }
    },
    [onSettled],
  );

  return {
    phase,
    routing,
    draftText,
    sources,
    infographics,
    elapsedMs,
    conversationId: activeConversationId,
    assistantMessageId,
    error,
    ask,
    abort,
    reset,
  };
}
