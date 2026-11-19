import { useState, type ReactNode } from 'react';
import { ChevronDown, FolderGit2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SearchSelect } from '@/components/ui/search-select';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { api } from '@/lib/http';
import type { DocumentUploadResponse } from '@/types/api';

/** 올릴 자리. 양식을 골라 올리면 그 양식의 산출물이 된다 */
export interface UploadTarget {
  wbsId: string;
  designatedId?: string;
}

/**
 * 올리기 단추(11-19 사용자 지시). 산출물은 파일을 직접 올리거나 저장소 파일을 골라 올린다.
 * 저장소 파일이 없는 사업은 바로 파일을 고른다.
 */
export function UploadMenu({
  hasRepo,
  onFile,
  onRepo,
  disabled,
  label = '올리기',
  variant = 'default',
}: {
  hasRepo: boolean;
  onFile: () => void;
  onRepo: () => void;
  disabled?: boolean;
  label?: string;
  variant?: 'default' | 'outline';
}): ReactNode {
  if (!hasRepo) {
    return (
      <Button size="sm" variant={variant} disabled={disabled} onClick={onFile}>
        {label}
      </Button>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant={variant} disabled={disabled}>
          {label}
          <ChevronDown className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onFile}>
          <Upload className="size-4" />
          파일 선택
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onRepo}>
          <FolderGit2 className="size-4" />
          저장소 파일 선택
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** 저장소 파일을 골라 그 작업(또는 양식)의 산출물로 올린다. 서버가 저장소에서 받아 남긴다 */
export function RepoPickDialog({
  projectId,
  target,
  paths,
  onClose,
  onDone,
}: {
  projectId: string;
  target: UploadTarget | null;
  paths: string[];
  onClose: () => void;
  onDone: (wbsId: string) => void;
}): ReactNode {
  const { toast } = useToast();
  const [path, setPath] = useState('');
  const [busy, setBusy] = useState(false);

  const close = () => {
    setPath('');
    onClose();
  };

  const submit = async () => {
    if (!target || !path) return;
    setBusy(true);
    try {
      await api.post<DocumentUploadResponse>(
        `/projects/${projectId}/documents/from-repository`,
        target.designatedId
          ? { path, designatedId: target.designatedId }
          : { path, wbsId: target.wbsId },
      );
      onDone(target.wbsId);
      close();
    } catch (err) {
      toast({
        title: '올리지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>저장소 파일 선택</DialogTitle>
        </DialogHeader>
        <div className="min-w-0">
          <SearchSelect
            options={paths.map((p) => ({ key: p, label: p }))}
            value={path}
            onChange={setPath}
            placeholder="검색"
            emptyText="맞는 파일이 없습니다"
            label="저장소 파일"
          />
        </div>
        <DialogFooter>
          <Button disabled={!path || busy} onClick={() => void submit()}>
            {busy ? '올리는 중…' : '올리기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
