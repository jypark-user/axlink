import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowUp, Square, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/common/toaster';
import { BACKDROP_SLOT_ID, RESOURCE_DOCK_ID } from '@/components/layout/app-shell';
import { useOptionalProject } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { toQueryString } from '@/lib/query';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import { AnswerBody, SourceEvidence } from '@/features/ax-query/answer-body';
import { ComposerActions } from '@/features/ax-query/composer-actions';
import { ResourcePanel, type PanelView } from '@/features/ax-query/resource-panel';
import { MentionMenu, useProjectMentions } from '@/features/ax-query/project-mentions';
import { ResourceSheet } from '@/features/ax-query/resource-sheet';
import { useAskStream } from '@/features/ax-query/use-ask-stream';
import type {
  ConversationResponse,
  MessageFeedback,
  MessageResponse,
  MessageSourceResponse,
  PageResponse,
  SuggestedQuestionsResponse,
} from '@/types/api';

const MAX_INPUT_HEIGHT = 176;

/** 답변을 기다리는 동안의 점 세 개. */
function TypingDots({ label }: { label: string }): ReactNode {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="bg-muted-foreground/50 size-1.5 rounded-full [animation:ax-typing_1.1s_ease-out_infinite]"
            style={{ animationDelay: `${dot * 0.15}s` }}
          />
        ))}
      </span>
      <span className="text-muted-foreground text-sm">{label}</span>
    </div>
  );
}

function PromptChips({
  prompts,
  onSelect,
  disabled,
}: {
  prompts: string[];
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}): ReactNode {
  return (
    <ul className="flex flex-wrap gap-2">
      {prompts.map((prompt) => (
        <li key={prompt}>
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => onSelect(prompt)}
            className="text-sm text-muted-foreground hover:text-primary h-auto rounded-full px-3.5 py-[7px] font-normal whitespace-normal"
          >
            {prompt}
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function AskPage(): ReactNode {
  const { conversationId, projectId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const project = useOptionalProject();
  const basePath = projectId ? `/p/${projectId}/ask` : '/ask';
  const projectScope = useMemo(() => (projectId ? [projectId] : []), [projectId]);

  const [question, setQuestion] = useState('');
  const [activeFootnote, setActiveFootnote] = useState<number | null>(null);
  const [panel, setPanel] = useState<PanelView | null>(null);
  const [panelSources, setPanelSources] = useState<MessageSourceResponse[]>([]);
  const [messagesNonce, setMessagesNonce] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  // 사업 안에서는 질문 범위가 그 사업으로 고정이라 멘션을 열지 않는다.
  // 멘션은 범위가 아직 안 정해진 자리에서만 쓴다 — 사업 밖의 새 질문.
  // 이미 시작한 대화는 만들 때 범위가 굳었고, 사업 안에서는 그 사업으로 정해져 있다.
  const canMention = !projectId && !conversationId;
  const mentions = useProjectMentions(question, setQuestion, inputRef, canMention);
  const [dock, setDock] = useState<HTMLElement | null>(null);
  const [backdrop, setBackdrop] = useState<HTMLElement | null>(null);
  /** 보냈지만 아직 서버 목록에 없는 질문. 서버 것이 도착하면 자리를 내준다. */
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    setDock(document.getElementById(RESOURCE_DOCK_ID));
    setBackdrop(document.getElementById(BACKDROP_SLOT_ID));
  }, []);

  const conversations = useAsync<PageResponse<ConversationResponse>>(
    () => api.get<PageResponse<ConversationResponse>>('/conversations?size=50'),
    [],
  );

  const messages = useAsync<MessageResponse[]>(
    () =>
      conversationId
        ? api.get<MessageResponse[]>(`/conversations/${conversationId}/messages`)
        : Promise.resolve([]),
    [conversationId, messagesNonce],
  );

  const suggestions = useAsync<SuggestedQuestionsResponse>(
    () =>
      api.get<SuggestedQuestionsResponse>(
        `/conversations/suggestions${toQueryString({ projectIds: projectScope })}`,
      ),
    [projectId],
  );

  const onSettled = useCallback(() => {
    setMessagesNonce((n) => n + 1);
    conversations.reload();
  }, [conversations]);

  const stream = useAskStream(onSettled);
  const { abort, reset, phase } = stream;

  useEffect(() => {
    if (phase === 'finalizing' && messages.data && messages.data.length > 0) reset();
  }, [phase, messages.data, reset]);

  /**
   * '새 질문' 은 대화 하나를 새로 여는 자리다. 이미 이 화면에 있어도 다시 누르면
   * 빈 자리에서 시작해야 하므로, 대화가 없는 주소로 올 때마다 쓰던 것을 비운다.
   */
  useEffect(() => {
    if (conversationId) return;
    setQuestion('');
    setPending(null);
    setActiveFootnote(null);
    setPanel(null);
    setPanelSources([]);
    mentions.clear();
    abort(); // 답변을 받는 중이었다면 끊고 나온다.
    reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key, conversationId]);

  // 입력줄은 내용만큼 자란다.
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, MAX_INPUT_HEIGHT)}px`;
  }, [question]);

  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.data, stream.draftText, pending]);

  const send = async (text: string) => {
    const body = text.trim();
    if (!body || stream.phase === 'streaming') return;
    const scope = mentions.scope.length > 0 ? mentions.scope : projectScope;
    setQuestion('');
    // 서버를 기다리지 않고 먼저 건다 — 대화방을 새로 여는 왕복이 앞에 있어 그냥 두면 한참 비어 있다.
    setPending(body);
    try {
      let target = conversationId;
      if (!target) {
        const created = await api.post<ConversationResponse>('/conversations', {
          title: body.slice(0, 60),
          projectScope: scope,
        });
        target = created.id;
        conversations.reload();
        void navigate(`${basePath}/${created.id}`, { replace: true });
      }
      await stream.ask(target, { question: body, projectScope: scope });
    } catch (e) {
      // 못 보냈으면 건 말풍선을 걷고 쓰던 글을 돌려준다.
      setPending(null);
      setQuestion(body);
      toast({
        title: '질문을 보내지 못했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    }
  };

  const openEvidence = (sources: MessageSourceResponse[]) => (footnoteNo: number) => {
    setPanelSources(sources);
    setActiveFootnote(footnoteNo);
    setPanel('evidence');
  };

  const rate = async (messageId: string, feedback: MessageFeedback) => {
    try {
      await api.post<void>(`/messages/${messageId}/feedback`, { feedback });
      setMessagesNonce((n) => n + 1);
    } catch {
      toast({ title: '피드백을 저장하지 못했습니다.', variant: 'error' });
    }
  };

  const streaming = stream.phase === 'streaming';
  const list = messages.data ?? [];
  const answering = streaming || Boolean(stream.draftText);
  // 서버 목록에 같은 질문이 들어오는 순간 건 말풍선은 사라진다 — 두 개가 겹치지 않는다.
  const pendingShown =
    pending !== null && !list.some((m) => m.role === 'USER' && m.content === pending);
  const isEmpty = list.length === 0 && !answering && !pendingShown;

  const composer = (
    <div className="relative">
      <MentionMenu mentions={mentions} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
        className="focus-within:border-ring border-input bg-card flex items-end gap-2 rounded-[26px] border p-2 transition-colors"
      >
        <ComposerActions
          targetName={project?.name ?? null}
          onOpenScreen={(view) => setPanel(view)}
        />

        <Label htmlFor="ax-query-input" className="sr-only">
          질문 입력
        </Label>
        <Textarea
          ref={inputRef}
          id="ax-query-input"
          rows={1}
          enterKeyHint="send"
          value={question}
          onChange={mentions.onChange}
          onKeyDown={(e) => {
            // 한글은 마지막 글자가 조합 중일 때 Enter 가 먼저 온다.
            // 그때 보내면 조합이 끝난 글자가 비워진 입력줄에 다시 떨어진다.
            if (e.nativeEvent.isComposing) return;
            if (mentions.onKeyDown(e)) return;
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send(question);
            }
          }}
          placeholder={
            project
              ? `${project.name}에 대해 물어보세요.`
              : canMention
                ? '무엇이든 물어보세요. @로 프로젝트를 고를 수 있습니다.'
                : '참여 중인 모든 프로젝트에 대해 물어보세요.'
          }
          className="text-base leading-7 min-h-0 flex-1 resize-none self-center border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
        />

        {streaming ? (
          <Button
            type="button"
            variant="secondary"
            size="icon"
            onClick={stream.abort}
            title="답변 중지"
            className="rounded-full"
          >
            <span className="sr-only">답변 중지</span>
            <Square />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!question.trim()}
            title="질문 보내기"
            className="rounded-full"
          >
            <span className="sr-only">질문 보내기</span>
            <ArrowUp />
          </Button>
        )}
      </form>
    </div>
  );

  const chat = isEmpty ? (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-6 pt-12 pb-24">
        <h2 className="text-muted-foreground text-center text-[26px] leading-[1.45] font-light tracking-[-0.02em] sm:text-[30px]">
          <span className="block">
            {project ? (
              <>
                <span className="text-foreground font-semibold">{project.name}</span>에 대해
              </>
            ) : (
              <>
                <span className="text-foreground font-semibold">참여 중인 모든 프로젝트</span>
                에서
              </>
            )}
          </span>
          <span className="block">
            <span className="text-foreground font-semibold">무엇이든</span> 물어보십시오
          </span>
        </h2>

        <div className="mt-8">{composer}</div>

        {!project && (
          <p className="text-muted-foreground text-sm mt-3 text-center">
            참여 중인 모든 프로젝트의 자료에서 답을 찾습니다.
            {canMention
              ? ' 한 곳만 보려면 @로 그 프로젝트를 부르십시오.'
              : ' 한 곳만 보려면 위쪽 ‘프로젝트 선택’에서 고르십시오.'}
          </p>
        )}

        <div className="mt-8">
          <PromptChips
            prompts={suggestions.data?.questions ?? []}
            onSelect={send}
            disabled={streaming}
          />
        </div>
      </div>
    </div>
  ) : (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={streamRef} className="min-h-0 flex-1 overflow-y-auto py-6">
        <div className="mx-auto w-full max-w-4xl space-y-6 px-6">
          {list.map((m) =>
            m.role === 'USER' ? (
              <div key={m.id} className="flex justify-end">
                <p className="bg-accent text-foreground text-base leading-7 max-w-[85%] rounded-lg px-4 py-3 whitespace-pre-line">
                  {m.content}
                </p>
              </div>
            ) : (
              <div key={m.id} className="min-w-0">
                {m.routing && (
                  <p className="text-muted-foreground text-xs font-semibold tracking-wide mb-2">
                    {m.routing.type}
                  </p>
                )}
                <AnswerBody
                  content={m.content}
                  sources={m.sources}
                  infographic={m.infographic}
                  onFootnoteClick={openEvidence(m.sources)}
                />
                <SourceEvidence
                  sources={m.sources}
                  activeFootnote={panel === 'evidence' ? activeFootnote : null}
                  onSelect={openEvidence(m.sources)}
                />
                <div className="mt-3 flex gap-1">
                  {(
                    [
                      ['UP', ThumbsUp, '도움이 됨'],
                      ['DOWN', ThumbsDown, '도움이 안 됨'],
                    ] as const
                  ).map(([value, Icon, aria]) => (
                    <Button
                      key={value}
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={aria}
                      onClick={() => rate(m.id, value)}
                      className={cn(
                        'size-7',
                        m.feedback === value ? 'text-primary' : 'text-muted-foreground',
                      )}
                    >
                      <Icon className="size-4" />
                    </Button>
                  ))}
                </div>
              </div>
            ),
          )}

          {pendingShown && (
            <div className="flex justify-end">
              <p className="bg-accent text-foreground text-base leading-7 max-w-[85%] rounded-lg px-4 py-3 whitespace-pre-line">
                {pending}
              </p>
            </div>
          )}

          {answering && (
            <div className="min-w-0">
              {stream.draftText ? (
                <>
                  <AnswerBody
                    content={stream.draftText}
                    sources={stream.sources}
                    infographic={stream.infographic}
                    onFootnoteClick={openEvidence(stream.sources)}
                  />
                  <SourceEvidence
                    sources={stream.sources}
                    activeFootnote={panel === 'evidence' ? activeFootnote : null}
                    onSelect={openEvidence(stream.sources)}
                  />
                  {stream.phase === 'aborted' && (
                    <p className="text-muted-foreground text-xs font-semibold tracking-wide mt-2">
                      중지됨
                    </p>
                  )}
                </>
              ) : (
                <TypingDots label="산출물에서 근거를 찾는 중…" />
              )}
            </div>
          )}

          {stream.error && <p className="text-destructive text-sm">{stream.error.message}</p>}
        </div>
      </div>

      <div className="shrink-0 py-4">
        <div className="mx-auto w-full max-w-4xl px-6">{composer}</div>
      </div>
    </div>
  );

  return (
    <>
      {chat}

      {/* 아직 아무것도 묻지 않은 화면에서만 — 대화가 시작되면 걷힌다. */}
      {isEmpty && backdrop && createPortal(<div className="ax-aurora" aria-hidden />, backdrop)}

      {panel &&
        dock &&
        createPortal(
          <ResourceSheet label="자료">
            <ResourcePanel
              view={panel}
              onViewChange={setPanel}
              sources={panelSources}
              activeFootnote={activeFootnote}
              onSelectFootnote={setActiveFootnote}
              onClose={() => setPanel(null)}
            />
          </ResourceSheet>,
          dock,
        )}
    </>
  );
}
