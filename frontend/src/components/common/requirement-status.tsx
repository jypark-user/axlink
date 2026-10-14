import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { requirementStatusText } from '@/components/common/requirement-status-text';
import { badgeVariantFor } from '@/lib/labels';
import type { RequirementStatus, RequirementStatusBasis } from '@/types/api';

export function RequirementStatusBadge({
  status,
  basis,
}: {
  status: RequirementStatus;
  basis: RequirementStatusBasis | null | undefined;
}): ReactNode {
  const { text, note } = requirementStatusText(status, basis);
  if (!note) {
    return <Badge variant={badgeVariantFor(status)}>{text}</Badge>;
  }
  if (basis === 'CLIENT_DECIDED') {
    return (
      <span className="inline-flex flex-col items-start gap-0.5">
        <Badge variant={badgeVariantFor(status)}>{text}</Badge>
        <span className="text-primary text-[11px] leading-none">{note}</span>
      </span>
    );
  }
  return (
    <span
      className="inline-flex flex-col items-start gap-0.5"
      title="GitHub 이슈가 닫혀 있어 붙은 상태입니다. 구현이나 검증을 확인했다는 뜻은 아닙니다."
    >
      <Badge variant="outline">{text}</Badge>
      <span className="text-muted-foreground text-[11px] leading-none">{note}</span>
    </span>
  );
}
