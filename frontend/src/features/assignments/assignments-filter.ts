import type { AssignmentResponse } from '@/types/api';

/** 검색 칸 하나로 업체명, 사용자 이름, 아이디(로그인 이름)를 한꺼번에 찾는다(11-20). 대소문자는 가리지 않는다 */
export function filterAssignments(rows: AssignmentResponse[], query: string): AssignmentResponse[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((a) =>
    [a.contractorOrgName, a.userName, a.userEmail].some((v) => v?.toLowerCase().includes(q)),
  );
}
