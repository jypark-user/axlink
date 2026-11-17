import { useEffect, useState } from 'react';
import { api } from '@/lib/http';
import type { WorkProductChecklistResponse } from '@/types/api';

/** 22종 분류 이름. 화면 데이터는 API 에서 온다(인도 점검표와 같은 이름). */
export function useTypeNames(projectId: string): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    api
      .get<WorkProductChecklistResponse>(`/projects/${projectId}/work-products`)
      .then((res) => {
        if (!alive) return;
        setNames(Object.fromEntries(res.items.map((wp) => [wp.type, wp.displayName])));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [projectId]);
  return names;
}
