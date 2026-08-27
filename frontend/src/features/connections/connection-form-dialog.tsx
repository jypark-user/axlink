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
  const [baseUrl, setBaseUrl] = useState(connection?.baseUrl ?? '');
  const [targetResource, setTargetResource] = useState(connection?.targetResource ?? '');
  const [token, setToken] = useState('');
  const [pending, setPending] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  const credential = buildCredential(token);
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
      const types =
        res.detectedItemTypes.length > 0 ? ` · ${res.detectedItemTypes.join(', ')}` : '';
      setTestResult({
        ok: res.reachable,
        text: res.reachable ? `${res.resourceName}${types}` : res.resourceName,
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
                setTool(v as ToolKind);
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
              커넥터 구현 전이라 등록·수정만 되고 연결 테스트·동기화는 아직 동작하지 않습니다.
            </p>
          </div>
          <div className={FIELD}>
            <Label htmlFor="connName">이름</Label>
            <Input id="connName" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className={FIELD}>
            <Label htmlFor="connBaseUrl">베이스 URL</Label>
            <Input
              id="connBaseUrl"
              required
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
              placeholder={connection?.credentialMasked}
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
