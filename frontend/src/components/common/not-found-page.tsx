import { type ReactNode } from 'react';
import { Compass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';

export function NotFoundPage(): ReactNode {
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <Compass className="size-10 text-muted-foreground" />
      <h1 className="text-lg font-semibold">페이지를 찾을 수 없습니다</h1>
      <p className="text-sm text-muted-foreground">요청하신 화면이 존재하지 않습니다.</p>
      <Button onClick={() => navigate('/projects', { replace: true })}>프로젝트 목록으로</Button>
    </div>
  );
}
