import type { ReactNode } from 'react';
import { FileSpreadsheet } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { formatDateTime } from '@/lib/format';
import type { WbsScheduleResponse } from '@/types/api';

const TOOL_NAME: Record<string, string> = {
  GITHUB: 'GitHub',
  GITLAB: 'GitLab',
  REDMINE: 'Redmine',
};

/**
 * 일정·진척 수치의 원천 (2026-11-18 사용자 지시). 이 화면의 수치는 화면에서 고치지 않는다. 원천 파일이
 * 바뀌어 다시 수집돼야 바뀐다. 용역사가 어느 파일을 고쳐야 하는지 헷갈리지 않게 파일과 읽은 판,
 * 반영되는 방법을 맨 위에 둔다.
 */
export function SourceFilePanel({ data }: { data: WbsScheduleResponse }): ReactNode {
  if (data.source === 'NONE') return null;
  const f = data.sourceFile ?? null;

  let where: ReactNode;
  let how: string;
  if (data.source === 'REDMINE') {
    where = <span className="font-medium">Redmine 이슈의 시작일·종료일·진척률</span>;
    how =
      'WBS 파일이 없어 Redmine 일정을 대신 씁니다. Redmine 이슈의 날짜·진척률을 고치면 다음 동기화 때 바뀝니다. WBS 엑셀이 있으면 위의 「WBS 올리기」로 올리세요.';
  } else if (f?.origin === 'REPOSITORY') {
    const tool = (f.tool && TOOL_NAME[f.tool]) ?? f.tool ?? '저장소';
    where = (
      <>
        {tool} 저장소 <span className="font-medium">{f.repository}</span>의{' '}
        <FileLink path={f.path} url={f.url} />
      </>
    );
    how =
      '용역사가 이 파일의 작업·기간·가중치·실적을 고쳐 저장소에 커밋하면, 다음 동기화 때 이 화면과 진척률이 바뀝니다. 다른 위치의 WBS 파일이나 이 화면에서 고친 값은 반영되지 않습니다.';
  } else if (f?.origin === 'UPLOAD') {
    where = (
      <>
        올린 파일 <FileLink path={f.path} url={f.url} />
      </>
    );
    how =
      '위의 「WBS 새 버전 올리기」로 고친 파일을 올리면 그 버전으로 바뀝니다. 이 화면에서 고친 값은 반영되지 않습니다.';
  } else {
    where = <FileLink path={f?.path ?? data.sourceLabel} url={f?.url ?? data.sourceUrl} />;
    how = '원천 파일이 바뀌어 다시 수집되면 이 화면과 진척률이 바뀝니다.';
  }

  const revision = f?.revision ?? data.planVersion;
  return (
    <Card className="mb-4 gap-0 py-3" data-testid="wbs-source">
      <CardContent className="flex gap-3 px-4">
        <FileSpreadsheet className="text-muted-foreground mt-0.5 size-5 shrink-0" />
        <div className="flex min-w-0 flex-col gap-1 text-sm">
          <p>
            <span className="win-label mr-2">수치의 원천</span>
            {where}
          </p>
          <p className="text-muted-foreground text-xs">
            {revision && (
              <>
                읽은 버전 <span className="tnum font-mono">{revision.slice(0, 12)}</span>
              </>
            )}
            {f?.readAt && <> · 반영 {formatDateTime(f.readAt)}</>}
            {f?.lastSyncedAt && <> · 마지막 동기화 {formatDateTime(f.lastSyncedAt)}</>}
            <> · 기준일 {data.baseDate}</>
          </p>
          <p className="text-muted-foreground text-xs">{how}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function FileLink({ path, url }: { path: string | null; url: string | null }): ReactNode {
  const text = <span className="font-mono">{path ?? '사업수행계획서'}</span>;
  if (!url) return <span className="font-medium">{text}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="text-primary font-medium underline-offset-2 hover:underline"
    >
      {text}
    </a>
  );
}
