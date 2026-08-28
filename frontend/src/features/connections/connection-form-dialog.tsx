import { useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { cn } from '@/lib/utils';
import type {
  ToolConnectionResponse,
  ToolConnectionTestResponse,
  ToolCredentialRequest,
  ToolKind,
} from '@/types/api';

const FIELD = 'flex flex-col gap-1.5';
const RESULT = 'whitespace-pre-wrap rounded p-2 font-mono text-xs';

const TOOL_OPTIONS: { value: ToolKind; label: string }[] = [
  { value: 'GITHUB', label: 'GitHub' },
  { value: 'REDMINE', label: 'Redmine' },
];

/**
 * 도구별 베이스 URL 기본값. GitHub는 저장소가 몇 개든 api.github.com 하나라 자동으로 채운다.
 * Redmine은 사내 설치마다 주소가 달라 기본값이 없다(직접 입력).
 * 사내 GitHub Enterprise면 https://<host>/api/v3 로 바꾸면 된다.
 */
const DEFAULT_BASE_URL: Record<ToolKind, string> = {
  GITHUB: 'https://api.github.com',
  REDMINE: '',
};

const AUTO_FILLED = new Set(Object.values(DEFAULT_BASE_URL).filter(Boolean));

/** 커넥터가 돌려주는 항목 종류를 발주기관 어휘로 옮긴다. */
const ITEM_LABELS: Record<string, string> = {
  issue: '이슈',
  pull_request: '풀 리퀘스트(PR)',
  commit: '커밋',
};

/** 도구별 입력 예시. 박PM이 무엇을 넣는지 필드에서 바로 알게 한다. */
const TOOL_HINTS: Record<ToolKind, { name: string; baseUrl: string; resource: string; token: string }> = {
  GITHUB: {
    name: '예: 백엔드 저장소',
    baseUrl: 'https://api.github.com',
    resource: 'owner/repo — 예: jypark-user/axlink',
    token: 'ghp_ 로 시작하는 Personal Access Token',
  },
  REDMINE: {
    name: '예: 사업 관리 Redmine',
    baseUrl: 'https://redmine.example.com',
    resource: '프로젝트 식별자 — 예: b-project',
    token: '내 계정 → API 액세스 키',
  },
};

/** GitHub(Personal Access Token) · Redmine(API Key) 둘 다 토큰 하나만 쓴다. */
export function buildCredential(token: string): ToolCredentialRequest | null {
  const trimmed = token.trim();
  return trimmed ? { accessToken: trimmed } : null;
}

export function ConnectionFormDialog({
  projectId,
  connection,
  open,
  onOpenChange,
  onSaved,
}: {
  projectId: string;
  connection?: ToolConnectionResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [tool, setTool] = useState<ToolKind>(connection?.tool ?? 'GITHUB');
  const [name, setName] = useState(connection?.name ?? '');
  const [baseUrl, setBaseUrl] = useState(
    connection?.baseUrl ?? DEFAULT_BASE_URL[connection?.tool ?? 'GITHUB'],
  );
  const [targetResource, setTargetResource] = useState(connection?.targetResource ?? '');
  const [token, setToken] = useState('');
  const [pending, setPending] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  const credential = buildCredential(token);
  const hint = TOOL_HINTS[tool];
  const canTest =
    credential !== null && baseUrl.trim() !== '' && targetResource.trim() !== '' && !testing;

  const runTest = async () => {
    if (!credential) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post<ToolConnectionTestResponse>('/connections/test', {
        tool,
        baseUrl: baseUrl.trim(),
        targetResource: targetResource.trim(),
        credential,
      });
      const items = res.detectedItemTypes.map((t) => ITEM_LABELS[t] ?? t).join(' · ');
      const detail = items ? `\n읽을 수 있는 항목: ${items}` : '';
      setTestResult({
        ok: res.reachable,
        text: res.reachable
          ? `✓ 연결 성공 — ${res.resourceName}${detail}`
          : res.resourceName,
      });
    } catch (err) {
      setTestResult({ ok: false, text: isApiError(err) ? err.message : String(err) });
    } finally {
      setTesting(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!connection && !credential) {
      toast({ title: '인증 정보를 입력하세요.', variant: 'error' });
      return;
    }
    setPending(true);
    try {
      if (connection) {
        await api.patch<ToolConnectionResponse>(`/connections/${connection.id}`, {
          name: name.trim(),
          baseUrl: baseUrl.trim(),
          targetResource: targetResource.trim(),
          credential,
        });
      } else {
        await api.post<ToolConnectionResponse>(`/projects/${projectId}/connections`, {
          tool,
          name: name.trim(),
          baseUrl: baseUrl.trim(),
          targetResource: targetResource.trim(),
          credential,
        });
      }
      toast({
        title: connection ? '연결을 수정했습니다.' : '연결을 등록했습니다.',
        variant: 'success',
      });
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast({
        title: '저장에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{connection ? '연동 수정' : '연동 등록'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className={FIELD}>
            <Label htmlFor="connTool">도구 유형</Label>
            <Select
              value={tool}
              onValueChange={(v) => {
                const next = v as ToolKind;
                setTool(next);
                // 사용자가 직접 넣은 주소는 지키고, 비었거나 자동으로 채운 값만 새 도구 기본값으로 바꾼다.
                setBaseUrl((prev) => (prev === '' || AUTO_FILLED.has(prev) ? DEFAULT_BASE_URL[next] : prev));
                setToken('');
                setTestResult(null);
              }}
              disabled={connection !== undefined}
            >
              <SelectTrigger id="connTool">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TOOL_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              읽기 전용으로 연결합니다. AX Link는 저장소에 아무것도 쓰지 않습니다 — 커밋·이슈·PR 조회만 합니다.
              수집(동기화)은 다음 단계에서 열립니다.
            </p>
          </div>
          <div className={FIELD}>
            <Label htmlFor="connName">이름</Label>
            <Input
              id="connName"
              required
              placeholder={hint.name}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className={FIELD}>
            <Label htmlFor="connBaseUrl">베이스 URL</Label>
            <Input
              id="connBaseUrl"
              required
              placeholder={hint.baseUrl}
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setTestResult(null);
              }}
            />
          </div>
          <div className={FIELD}>
            <Label htmlFor="connResource">대상 리소스</Label>
            <Input
              id="connResource"
              required
              placeholder={hint.resource}
              value={targetResource}
              onChange={(e) => {
                setTargetResource(e.target.value);
                setTestResult(null);
              }}
            />
          </div>
          <div className={FIELD}>
            <Label htmlFor="connToken">액세스 토큰</Label>
            <Input
              id="connToken"
              type="password"
              autoComplete="new-password"
              placeholder={connection?.credentialMasked ?? hint.token}
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setTestResult(null);
              }}
            />
          </div>
          {testResult && (
            <p
              className={cn(
                RESULT,
                testResult.ok
                  ? 'bg-muted text-muted-foreground'
                  : 'bg-destructive/10 text-destructive',
              )}
            >
              {testResult.text}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={!canTest} onClick={runTest}>
              연결 테스트
            </Button>
            <Button type="submit" disabled={pending}>
              {connection ? '저장' : '등록'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
