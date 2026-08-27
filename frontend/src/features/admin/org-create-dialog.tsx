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
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import type { OrganizationResponse, OrgType } from '@/types/api';

/** 조직 등록. 유형(발주사/용역사)은 호출하는 메뉴가 정한다. */
export function OrgCreateDialog({
  type,
  open,
  onOpenChange,
  onCreated,
}: {
  type: OrgType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [businessNo, setBusinessNo] = useState('');
  const [pending, setPending] = useState(false);
  const typeLabel = type === 'CLIENT' ? '발주사' : '용역사';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    try {
      await api.post<OrganizationResponse>('/organizations', {
        name: name.trim(),
        type,
        businessNo: businessNo.trim() || null,
      });
      toast({ title: `${typeLabel}를 등록했습니다.`, variant: 'success' });
      setName('');
      setBusinessNo('');
      onOpenChange(false);
      onCreated();
    } catch (err) {
      toast({
        title: '등록에 실패했습니다.',
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
          <DialogTitle>{typeLabel} 등록</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="orgName">이름</Label>
            <Input id="orgName" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="orgBusinessNo">사업자번호</Label>
            <Input
              id="orgBusinessNo"
              value={businessNo}
              onChange={(e) => setBusinessNo(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              등록
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
