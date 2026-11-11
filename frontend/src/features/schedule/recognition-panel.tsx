import type { ReactNode } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Window } from '@/components/ui/window';
import { formatDateTime } from '@/lib/format';
import type { WbsRecognitionResponse } from '@/types/api';

/**
 * 계획서 인식 결과 (IM-007 UC-030 3단계, AC-030-4). DEC-04 (b): 확인·열 재지정 단계는 없고,
 * 어떻게 읽었는지와 경고를 보여 준다. 고칠 것이 있으면 원본을 고쳐 다시 수집한다.
 * 읽지 못한 판은 사유를 보이고 작업 0건·진척 0% 로 보이지 않는다.
 */
export function RecognitionPanel({
  recognition: r,
  shownLeaves,
}: {
  recognition: WbsRecognitionResponse;
  /** 화면에 보이는 말단 작업 수. 직전 판을 쓰고 있을 때 몇 건인지 알린다 */
  shownLeaves: number;
}): ReactNode {
  const version = r.planVersion ? `버전 ${r.planVersion}` : '현행 판';
  let hint: string | undefined;
  if (r.status === 'OK')
    hint = r.readAt ? `${version} · ${formatDateTime(r.readAt)} 읽음` : version;
  return (
    <Window title="계획서 인식 결과" hint={hint} className="pt-0">
      {r.status === 'FAILED' ? (
        <Alert variant="destructive" className="mb-3" data-testid="recognition-failed">
          <AlertTitle>계획서({version})를 읽지 못했습니다</AlertTitle>
          <AlertDescription>
            <p>{r.error}</p>
            <p className="mt-1">
              {r.usingPrevious
                ? `직전에 읽은 계획서의 작업 ${shownLeaves}개를 이전 기준선으로 계속 씁니다.`
                : '읽은 작업이 없어 WBS 기준 진척률은 산출하지 않습니다. 진척률 칸은 「산출 불가」로 둡니다.'}
            </p>
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <dl
            className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm"
            data-testid="recognition-facts"
          >
            <Fact label="말단 작업" value={`${r.leafCount ?? '-'}개`} />
            <Fact label="묶음" value={`${r.groupCount ?? '-'}개`} />
            <Fact
              label="가중치 합"
              value={
                r.weightTotal == null
                  ? '-'
                  : `${r.weightTotal.toFixed(3)}${r.normalized ? ' (합으로 나눠 맞춤)' : ''}`
              }
              warn={r.normalized}
            />
            <Fact
              label="산출물 미지정"
              value={`${r.missingDeliverableCount ?? '-'}개`}
              warn={(r.missingDeliverableCount ?? 0) > 0}
            />
            {r.headerRow != null && <Fact label="머리글" value={`${r.headerRow}행`} />}
          </dl>
          {r.columns.length > 0 && (
            <table className="mb-3 w-full max-w-xl text-sm" data-testid="recognition-columns">
              <thead className="text-muted-foreground text-xs">
                <tr>
                  <th className="py-1 pr-4 text-left font-medium">항목</th>
                  <th className="py-1 pr-4 text-left font-medium">읽은 머리글</th>
                  <th className="py-1 text-left font-medium">열</th>
                </tr>
              </thead>
              <tbody>
                {r.columns.map((c) => (
                  <tr key={c.field} className="border-t">
                    <td className="py-1 pr-4">{c.label}</td>
                    <td className="py-1 pr-4">
                      {c.header ?? <span className="text-muted-foreground">없음</span>}
                    </td>
                    <td className="tnum py-1">{c.column ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {r.columns.length === 0 && r.recordedBeforeTracking && (
            <p className="text-muted-foreground mb-3 text-sm">
              이 판은 인식 결과를 남기기 전에 읽어 열 매핑 기록이 없습니다. 새 버전을 수집하면
              보입니다.
            </p>
          )}
        </>
      )}
      {r.warnings.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-sm" data-testid="recognition-warnings">
          {r.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <p className="text-muted-foreground text-xs">{r.guidance}</p>
    </Window>
  );
}

function Fact({ label, value, warn }: { label: string; value: string; warn?: boolean }): ReactNode {
  return (
    <div className="flex gap-1.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={warn ? 'tnum text-destructive font-medium' : 'tnum font-medium'}>{value}</dd>
    </div>
  );
}
