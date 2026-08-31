import { useEffect, useState, type ReactNode, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/features/auth/auth-context';
import { previewInvitation } from '@/api/auth';
import { isApiError } from '@/lib/api-error';
import type { InvitationPreviewResponse } from '@/types/api';

export function InviteAcceptPage(): ReactNode {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const { acceptInvite } = useAuth();

  const [preview, setPreview] = useState<InvitationPreviewResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [orgName, setOrgName] = useState('');
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!token) {
      setLoadError('초대 링크가 유효하지 않습니다.');
      setLoading(false);
      return;
    }
    let cancelled = false;
    previewInvitation(token)
      .then((p) => {
        if (!cancelled) setPreview(p);
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadError(isApiError(e) ? e.message : '초대 정보를 불러올 수 없습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // USER 초대는 계정이 이미 있다. 비밀번호만 정하면 된다.
  const isNewAccount = preview?.kind === 'PROJECT';

  const validate = (): string | null => {
    if (isNewAccount && !orgName.trim()) return '회사명을 입력하세요.';
    if (isNewAccount && !name.trim()) return '이름을 입력하세요.';
    if (isNewAccount && !username.trim()) return '아이디를 입력하세요.';
    if (password.length < 8) return '비밀번호는 8자 이상이어야 합니다.';
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
      return '영문과 숫자를 모두 포함해야 합니다.';
    if (password !== confirm) return '비밀번호 확인이 일치하지 않습니다.';
    return null;
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validate();
    if (v) {
      setFormError(v);
      return;
    }
    setFormError(null);
    setPending(true);
    try {
      await acceptInvite(
        isNewAccount
          ? {
              token,
              contractorOrgName: orgName.trim(),
              username: username.trim(),
              name: name.trim(),
              password,
            }
          : { token, password },
      );
      void navigate('/projects', { replace: true });
    } catch (err) {
      setFormError(isApiError(err) ? err.message : '계정 생성에 실패했습니다.');
    } finally {
      setPending(false);
    }
  };

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>{isNewAccount ? '계정 만들기' : '비밀번호 설정'}</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : loadError ? (
          <Alert variant="destructive">
            <AlertTitle>초대 오류</AlertTitle>
            <AlertDescription className="flex flex-col gap-2">
              <span>{loadError}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate('/login', { replace: true })}
              >
                로그인으로 이동
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <p className="font-medium">{isNewAccount ? preview?.projectName : preview?.name}</p>
              <p className="text-muted-foreground">
                {isNewAccount
                  ? '이 사업에 용역사로 참여합니다.'
                  : `${preview?.username} · ${preview?.organizationName}`}
              </p>
            </div>
            {formError && (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}
            {isNewAccount && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="orgName">회사명</Label>
                  <Input
                    id="orgName"
                    autoComplete="organization"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="name">이름</Label>
                  <Input
                    id="name"
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="username">아이디</Label>
                  <Input
                    id="username"
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>
              </>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="confirm">비밀번호 확인</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={pending}>
              {pending
                ? '처리 중…'
                : isNewAccount
                  ? '계정 만들고 시작하기'
                  : '비밀번호 설정하고 시작하기'}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
