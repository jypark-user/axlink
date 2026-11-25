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
import { useAuth } from '@/features/auth/auth-context';
import { isApiError } from '@/lib/api-error';
import { api } from '@/lib/http';
import type { BaselineResponse } from '@/types/api';

const ACCEPT = '.hwp,.hwpx,.docx,.xlsx,.pptx,.pdf,.md,.txt';

/**
 * 요구사항 명세서 올리기(11-25 사용자 지시). 일정 화면의 WBS 올리기처럼 요구사항 화면에서 파일을
 * 바로 올린다. 자료 화면에 먼저 올려 두고 고르던 순서는 번거로웠다. 서버가 파일을 문서로 저장하고
 * 항목을 뽑아 정리 중 명세서를 만든다. 정리·제출은 요구사항 등록·확정 화면에서 용역사가 이어 한다.
 * 발주기관도 올릴 수 있다(11-25 사용자 결정).
 */
export function SpecUploadButton({
  projectId,
  onUploaded,
  variant = 'outline',
}: {
  projectId: string;
  onUploaded: (b: BaselineResponse) => void;
  variant?: 'outline' | 'default';
}): ReactNode {
  const { toast } = useToast();
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setFile(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const submit = async () => {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setBusy(true);
    setError(null);
    try {
      const res = await api.upload<BaselineResponse>(
        `/projects/${projectId}/requirement-baseline/upload`,
        form,
      );
      toast({
        title: '요구사항 명세서를 등록했습니다.',
        // 발주기관이 올린 명세서도 정리·제출은 용역사가 한다(DEC-05, 11-25)
        description:
          me?.role === 'CLIENT'
            ? `항목 ${res.items.length}건을 뽑았습니다. 용역사가 정리해 제출하면 확정합니다.`
            : `항목 ${res.items.length}건을 뽑았습니다. 확인하고 정리한 뒤 제출하세요.`,
        variant: 'success',
      });
      setOpen(false);
      reset();
      onUploaded(res);
    } catch (err) {
      setError(isApiError(err) ? err.message : '올리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button size="sm" variant={variant} onClick={() => setOpen(true)}>
        <Upload />
        요구사항 명세서 올리기
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
            <DialogTitle>요구사항 명세서 올리기</DialogTitle>
            <DialogDescription>
              올린 파일에서 요구사항 항목을 뽑습니다. 뽑은 목록은 발주기관이 확정해야 요구사항이
              됩니다.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="specFile">파일</Label>
              <Input
                id="specFile"
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setError(null);
                }}
              />
              <p className="text-muted-foreground text-xs">
                HWP, HWPX, DOCX, XLSX, PDF 등 50MB 이하
              </p>
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
