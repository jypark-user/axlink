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
import type { OrganizationResponse, Role, UserResponse } from '@/types/api';

/**
 * 계정 생성. 역할은 호출하는 메뉴가 정한다.
 * organizations 를 주면 소속을 고르게 하고, fixedOrganization 을 주면 그 조직에 바로 만든다.
 */
export function UserCreateDialog({
  role,
  organizations,
  fixedOrganization,
  open,
  onOpenChange,
  onCreated,
}: {
  role: Role;
  organizations?: OrganizationResponse[];
  fixedOrganization?: OrganizationResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [organizationId, setOrganizationId] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [pending, setPending] = useState(false);

  const targetOrgId = fixedOrganization?.id ?? organizationId;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!targetOrgId) {
      toast({ title: '소속을 선택하세요.', variant: 'error' });
      return;
    }
    setPending(true);
    try {
      await api.post<UserResponse>('/users', {
        organizationId: targetOrgId,
        email: email.trim(),
        name: name.trim(),
        role,
      });
      toast({ title: '계정을 생성하고 초대를 보냈습니다.', variant: 'success' });
      setEmail('');
      setName('');
      onOpenChange(false);
      onCreated();
    } catch (err) {
      toast({
        title: '생성에 실패했습니다.',
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
          <DialogTitle>
            {fixedOrganization ? `${fixedOrganization.name} 계정 생성` : '계정 생성'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          {!fixedOrganization && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="userOrg">소속</Label>
              <Select value={organizationId} onValueChange={setOrganizationId}>
                <SelectTrigger id="userOrg">
                  <SelectValue placeholder="선택" />
                </SelectTrigger>
                <SelectContent>
                  {(organizations ?? []).map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="userEmail">이메일</Label>
            <Input
              id="userEmail"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="userName">이름</Label>
            <Input id="userName" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              생성
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
