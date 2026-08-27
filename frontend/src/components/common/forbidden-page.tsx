import { type ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';

export function ForbiddenPage(): ReactNode {
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <ShieldAlert className="size-10 text-destructive" />
      <h1 className="text-lg font-semibold">접근 권한이 없습니다</h1>
      <p className="text-sm text-muted-foreground">이 화면에 접근할 수 있는 권한이 없습니다.</p>
      <Button onClick={() => navigate('/projects', { replace: true })}>프로젝트 목록으로</Button>
    </div>
  );
}
