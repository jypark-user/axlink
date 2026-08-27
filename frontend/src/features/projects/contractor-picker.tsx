import { api } from '@/lib/http';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { PageResponse, UserResponse } from '@/types/api';

/**
 * 기본 정보에 적은 용역사 이름과 맞는 조직을 찾는다. 앞뒤 공백·대소문자는 무시한다.
 * 맞는 곳이 없으면 null — 이름은 사업에 남고 계정 할당만 미룬다.
 */
export function matchContractor(
  name: string,
  users: UserResponse[],
): { contractorOrgId: string; userIds: string[] } | null {
  const key = name.trim().toLowerCase();
  if (!key) return null;
  const members = users.filter((u) => u.organizationName.trim().toLowerCase() === key);
  if (members.length === 0) return null;
  return { contractorOrgId: members[0].organizationId, userIds: members.map((u) => u.id) };
}

/** 용역사 계정 목록 — 기본 정보에 적은 이름과 맞는 계정을 찾는 데 쓴다. */
export function useContractorUsers() {
  return useAsync<PageResponse<UserResponse>>(
    () =>
      api.get<PageResponse<UserResponse>>(
        `/users${toQueryString({ role: 'CONTRACTOR', status: 'ACTIVE', size: 100 })}`,
      ),
    [],
  );
}
