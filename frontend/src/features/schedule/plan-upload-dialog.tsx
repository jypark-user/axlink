import { useRef, useState, type ReactNode } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { api } from '@/lib/http';
import type { WbsPlanUploadResponse } from '@/types/api';

/**
 * 일정 화면의 WBS 올리기(11-24 사용자 결정). 저장소가 없는 사업(Redmine 만 쓰는 업체 등)은 WBS
 * 엑셀을 여기서 올린다. 올린 파일이 곧바로 사업수행계획서의 현행 버전이 된다. 서버가 저장소 WBS 가
 * 있는 사업에는 planUpload 를 false 로 주므로 그때는 버튼을 그리지 않는다.
 */
export function PlanUploadButton({
  projectId,
  hasPlan,
  onUploaded,
}: {
  projectId: string;
  hasPlan: boolean;
  onUploaded: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setFile(null);
    setVersion('');
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const submit = async () => {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    if (version.trim()) form.append('version', version.trim());
    setBusy(true);
    setError(null);
    try {
      const res = await api.upload<WbsPlanUploadResponse>(`/projects/${projectId}/wbs/plan`, form);
      toast({
        title: `WBS ${res.version} 을(를) 반영했습니다.`,
        description: `작업 ${res.leafCount}개`,
        variant: 'success',
      });
      setOpen(false);
      reset();
      onUploaded();
    } catch (err) {
      setError(isApiError(err) ? err.message : '올리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Upload />
        {hasPlan ? 'WBS 새 버전 올리기' : 'WBS 올리기'}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) reset();
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{hasPlan ? 'WBS 새 버전 올리기' : 'WBS 올리기'}</DialogTitle>
            <DialogDescription>
              엑셀(.xlsx) 파일을 올리면 이 사업의 일정·진척 기준이 됩니다.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="planFile">파일</Label>
              <Input
                id="planFile"
                ref={inputRef}
                type="file"
                accept=".xlsx"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setError(null);
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="planVersion">버전</Label>
              <Input
                id="planVersion"
                value={version}
                maxLength={50}
                placeholder="예: v1.1 (비우면 오늘 날짜)"
                onChange={(e) => setVersion(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-destructive text-sm" role="alert">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              취소
            </Button>
            <Button onClick={() => void submit()} disabled={!file || busy}>
              {busy ? '올리는 중…' : '올리기'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
