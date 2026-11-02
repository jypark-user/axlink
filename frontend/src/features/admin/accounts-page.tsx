import { useState, type FormEvent, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { api } from '@/lib/http';
import { toQueryString } from '@/lib/query';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import type {
  ClientUserCreatedResponse,
  OrganizationResponse,
  PageResponse,
  UserResponse,
} from '@/types/api';

/**
 * 발주기관 조직과 담당자 계정 발급(GH-187). 최고관리자만 본다.
 * 용역사는 사업 초대 링크로 가입하므로 여기서는 발주기관만 만든다. 계정은 지우지 않고 중지한다.
 */
export function AccountsPage(): ReactNode {
  const { toast } = useToast();
  const orgs = useAsync<OrganizationResponse[]>(
    () => api.get<OrganizationResponse[]>('/admin/organizations?type=CLIENT'),
    [],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [orgName, setOrgName] = useState('');
  const [issued, setIssued] = useState<ClientUserCreatedResponse | null>(null);

  const createOrg = async (e: FormEvent) => {
    e.preventDefault();
    const name = orgName.trim();
    if (!name) return;
    try {
      const org = await api.post<OrganizationResponse>('/admin/organizations', { name });
      setOrgName('');
      setSelected(org.id);
      orgs.reload();
      toast({ title: `${org.name} 을(를) 만들었습니다.`, variant: 'success' });
    } catch (err) {
      toast({
        title: '조직을 만들지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <>
      <PageHeader
        title="발주기관·계정"
        description="발주기관 조직을 만들고 담당자 계정을 발급합니다. 용역사 계정은 사업의 초대 링크로 가입합니다. 계정은 지우지 않고 중지합니다."
      />
      <div className="grid gap-5 lg:grid-cols-[20rem_1fr]">
        <Card>
          <CardContent className="flex flex-col gap-4 pt-5">
            <form onSubmit={createOrg} className="flex flex-col gap-2">
              <Label htmlFor="org-name">새 발주기관</Label>
              <div className="flex gap-2">
                <Input
                  id="org-name"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="기관 이름"
                  maxLength={200}
                />
                <Button type="submit" size="sm" disabled={!orgName.trim()}>
                  만들기
                </Button>
              </div>
            </form>
            <DataState state={orgs} onRetry={orgs.reload}>
              {(list) =>
                list.length === 0 ? (
                  <p className="text-muted-foreground text-sm">발주기관이 없습니다.</p>
                ) : (
                  <ul className="flex flex-col gap-1" aria-label="발주기관 목록">
                    {list.map((o) => (
                      <li key={o.id}>
                        <button
                          type="button"
                          onClick={() => setSelected(o.id)}
                          aria-current={selected === o.id}
                          className={cn(
                            'hover:bg-accent flex w-full flex-col items-start rounded-md px-3 py-2 text-left',
                            selected === o.id && 'bg-accent',
                          )}
                        >
                          <span className="text-sm font-medium">{o.name}</span>
                          <span className="text-muted-foreground text-xs">
                            계정 {o.activeUserCount}/{o.userCount} · 사업 {o.projectCount}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              }
            </DataState>
          </CardContent>
        </Card>
        {selected ? (
          <OrgUsers
            key={selected}
            org={orgs.data?.find((o) => o.id === selected) ?? null}
            orgId={selected}
            onIssued={(u) => {
              setIssued(u);
              orgs.reload();
            }}
            onChanged={orgs.reload}
          />
        ) : (
          <p className="text-muted-foreground py-10 text-center text-sm">
            왼쪽에서 발주기관을 고르세요.
          </p>
        )}
      </div>
      <IssuedDialog user={issued} onClose={() => setIssued(null)} />
    </>
  );
}

function OrgUsers({
  org,
  orgId,
  onIssued,
  onChanged,
}: {
  org: OrganizationResponse | null;
  orgId: string;
  onIssued: (u: ClientUserCreatedResponse) => void;
  onChanged: () => void;
}): ReactNode {
  const { toast } = useToast();
  const users = useAsync<PageResponse<UserResponse>>(
    () =>
      api.get<PageResponse<UserResponse>>(
        `/users${toQueryString({ organizationId: orgId, size: 200 })}`,
      ),
    [orgId],
  );
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const issue = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await api.post<ClientUserCreatedResponse>('/admin/users', {
        organizationId: orgId,
        username: username.trim(),
        name: name.trim(),
      });
      setUsername('');
      setName('');
      users.reload();
      onIssued(u);
    } catch (err) {
      toast({
        title: '계정을 만들지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (u: UserResponse) => {
    const next = u.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    if (next === 'DISABLED' && !window.confirm(`${u.name}(${u.username}) 계정을 중지할까요?`)) {
      return;
    }
    try {
      await api.patch(`/admin/users/${u.id}/status`, { status: next });
      users.reload();
      onChanged();
    } catch (err) {
      toast({
        title: '상태를 바꾸지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <Card>
      <CardContent className="flex flex-col gap-5 pt-5">
        <h2 className="text-base font-semibold">{org?.name ?? '발주기관'} 담당자</h2>
        <form onSubmit={issue} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-username">아이디</Label>
            <Input
              id="new-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="영문·숫자·점·밑줄·하이픈"
              pattern="[A-Za-z0-9._\-]{3,60}"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-name">이름</Label>
            <Input
              id="new-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="담당자 이름"
              maxLength={100}
            />
          </div>
          <Button type="submit" disabled={busy || username.trim().length < 3 || !name.trim()}>
            계정 발급
          </Button>
        </form>
        <DataState state={users} onRetry={users.reload}>
          {(page) =>
            page.content.length === 0 ? (
              <p className="text-muted-foreground text-sm">아직 계정이 없습니다.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-muted-foreground text-left text-xs">
                  <tr>
                    <th className="py-2 font-normal">이름</th>
                    <th className="py-2 font-normal">아이디</th>
                    <th className="py-2 font-normal">상태</th>
                    <th className="py-2 font-normal">마지막 로그인</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {page.content.map((u) => (
                    <tr key={u.id} className="border-t">
                      <td className="py-2">{u.name}</td>
                      <td className="py-2 font-mono text-xs">{u.username}</td>
                      <td className="py-2">
                        <Badge variant={u.status === 'ACTIVE' ? 'success' : 'muted'}>
                          {u.status === 'ACTIVE' ? '사용 중' : '중지'}
                        </Badge>
                      </td>
                      <td className="text-muted-foreground tnum py-2 text-xs">
                        {u.lastLoginAt ? formatDateTime(u.lastLoginAt) : '-'}
                      </td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => void toggle(u)}>
                          {u.status === 'ACTIVE' ? '중지' : '다시 사용'}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </DataState>
      </CardContent>
    </Card>
  );
}

/** 첫 비밀번호는 지금 한 번만 보인다. 닫으면 다시 볼 수 없다. */
function IssuedDialog({
  user,
  onClose,
}: {
  user: ClientUserCreatedResponse | null;
  onClose: () => void;
}): ReactNode {
  const { toast } = useToast();
  const copy = async () => {
    if (!user) return;
    try {
      await navigator.clipboard.writeText(user.temporaryPassword);
      toast({ title: '복사했습니다.', variant: 'success' });
    } catch {
      toast({ title: '복사하지 못했습니다. 직접 옮겨 적으세요.', variant: 'error' });
    }
  };
  return (
    <Dialog open={user !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>계정을 발급했습니다</DialogTitle>
          <DialogDescription>
            첫 비밀번호는 이 창에서 한 번만 보입니다. 담당자에게 따로 전하고, 로그인한 뒤 바로
            바꾸도록 안내하세요.
          </DialogDescription>
        </DialogHeader>
        {user && (
          <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted-foreground">아이디</dt>
            <dd className="font-mono">{user.username}</dd>
            <dt className="text-muted-foreground">첫 비밀번호</dt>
            <dd className="font-mono break-all" data-testid="temporary-password">
              {user.temporaryPassword}
            </dd>
          </dl>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => void copy()}>
            비밀번호 복사
          </Button>
          <Button onClick={onClose}>닫기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
