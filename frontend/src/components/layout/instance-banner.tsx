import { useEffect, useState, type ReactNode } from 'react';

/**
 * 개발·검증 환경 표시 띠. 서버가 이름표를 줄 때만 보인다(공개 환경은 비어 있다).
 * 로그인 전에도 보여야 해서 토큰 없이 부르고, 실패하면 아무것도 그리지 않는다.
 */
export function InstanceBanner(): ReactNode {
  const [label, setLabel] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${import.meta.env.BASE_URL}api/instance`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { label: string | null } | null) => {
        if (alive && body?.label) setLabel(body.label);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  if (!label) return null;
  return (
    <div
      role="status"
      className="bg-warning-muted text-warning border-warning/40 border-b px-4 py-1 text-center text-xs font-semibold"
    >
      {label}
    </div>
  );
}
