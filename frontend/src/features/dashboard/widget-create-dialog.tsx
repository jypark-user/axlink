import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
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
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/http';
import { defaultGridItem } from '@/features/dashboard/layout-mapper';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import { label as labelOf } from '@/lib/labels';
import type {
  GridItem,
  WidgetDataResponse,
  WidgetGenerateResponse,
  WidgetResponse,
  WidgetSpec,
  WidgetTemplate,
} from '@/types/api';

function PreviewBody({ spec, data }: { spec: WidgetSpec; data: WidgetDataResponse }) {
  const Renderer = resolveWidgetRenderer(spec.template);
  if (data.rows.length === 0 && data.total === null) {
    return (
      <p className="text-muted-foreground py-6 text-center text-sm">
        조건에 맞는 데이터가 없습니다.
      </p>
    );
  }
  return <Renderer spec={spec} data={data} />;
}

export function WidgetCreateDialog({
  dashboardId,
  projectId,
  initialTemplate = null,
  editing = null,
  existing,
  onClose,
  onCreated,
}: {
  dashboardId: string;
  projectId: string;
  /** 편집 사이드바에서 고른 표시 형태 — 그 자리로 모달이 열린다. */
  initialTemplate?: WidgetTemplate | null;
  /** 고칠 위젯. 있으면 새로 만들지 않고 이 위젯을 고친다. */
  editing?: WidgetResponse | null;
  /** 지금 놓인 자리 — 새 위젯을 그 아래에 쌓으려면 알아야 한다. */
  existing: GridItem[];
  onClose: () => void;
  onCreated: () => void;
}) {
  // 모양은 사이드바에서 정해져 들어온다 — 여기서 바꾸지 않는다.
  // 고치는 중이면 그 위젯이 쓰던 모양을 그대로 이어 쓴다.
  const template = editing?.spec?.template ?? initialTemplate;
  const [title, setTitle] = useState(editing?.spec?.title ?? '');
  // 고치는 중이면 만들 때 적은 의도를 그대로 띄운다 — 무엇을 보려던 위젯인지 알고 고쳐야 한다.
  const [prompt, setPrompt] = useState(editing?.spec?.prompt ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [spec, setSpec] = useState<WidgetSpec | null>(editing?.spec ?? null);
  const [preview, setPreview] = useState<WidgetDataResponse | null>(null);
  const [rejection, setRejection] = useState<string | null>(null);

  // 고치는 중이면 지금 그려져 있는 값을 미리보기에 띄운다 —
  // 다시 생성하기 전에도 무엇을 고치는 중인지 보여야 한다.
  useEffect(() => {
    if (!editing) return;
    let alive = true;
    api
      .post<WidgetDataResponse>(`/widgets/${editing.id}/data`, {})
      .then((data) => {
        if (alive) setPreview(data);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [editing]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setRejection(null);
    try {
      const res = await api.post<WidgetGenerateResponse>('/widgets/generate', {
        prompt: prompt.trim(),
        template,
        projectScope: [projectId],
        dashboardId,
      });
      if (res.status === 'NOT_EXPRESSIBLE') {
        setRejection(
          res.rejection?.suggestedAction ?? res.rejection?.reason ?? '표현할 수 없습니다.',
        );
        setSpec(null);
        setPreview(null);
        return;
      }
      setSpec(res.spec);
      setPreview(res.preview);
      // 제목을 안 적었으면 지어 준 것을 채워 둔다 — 그대로 두거나 고쳐 쓰면 된다.
      if (!title.trim() && res.spec) setTitle(res.spec.title);
    } catch (e) {
      setError(e instanceof Error ? e.message : '생성에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const place = async () => {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      const named: WidgetSpec = {
        ...spec,
        title: title.trim() || spec.title,
        // 의도는 명세와 같이 저장한다. 비워 두면 전에 적은 것을 지킨다
        prompt: prompt.trim() || spec.prompt || null,
      };
      if (editing) {
        // 고치는 것은 명세만 바꾼다 — 자리와 크기는 그대로 둔다.
        await api.patch(`/widgets/${editing.id}`, { spec: named });
      } else {
        // 표시 형태마다 기본 크기가 다르고, 맨 아래에 쌓아야 이미 놓인 위젯과 겹치지 않는다.
        const gridItem = defaultGridItem('', spec.template, existing);
        await api.post(`/dashboards/${dashboardId}/widgets`, { spec: named, gridItem });
      }
      onCreated();
      onClose();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : editing ? '저장에 실패했습니다.' : '배치에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          {/* 모양은 사이드바에서 이미 골랐다 — 여기서는 무엇을 골랐는지만 보여준다. */}
          <DialogTitle className="flex items-center gap-2">
            {editing ? '위젯 수정' : '위젯 추가'}
            {template && (
              <Badge variant="outline" className="font-normal">
                {labelOf(template)}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="widget-title">제목</Label>
            <Input
              id="widget-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="비워 두면 내용에 맞춰 지어 줍니다"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="widget-prompt">표시할 내용</Label>
            <Textarea
              id="widget-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={3}
              placeholder={
                editing
                  ? '이 위젯을 만들 때 적은 의도가 없습니다. 바꿀 내용을 적고 다시 생성하세요'
                  : '예: 용역사별 이번 달 이슈 처리율'
              }
            />
          </div>

          {rejection && (
            <Alert>
              <AlertDescription>{rejection}</AlertDescription>
            </Alert>
          )}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {spec && preview && (
            <div className="flex flex-col gap-2">
              <Label>3. 미리보기</Label>
              <div className="rounded-lg border p-3">
                <PreviewBody spec={spec} data={preview} />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={generate} disabled={busy || prompt.trim().length === 0}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {spec ? '다시 생성' : '생성'}
          </Button>
          <Button onClick={place} disabled={busy || !spec}>
            {editing ? '저장' : '배치'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
