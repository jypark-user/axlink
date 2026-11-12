/**
 * 초안 「산출물로 제출」 전 확인. 확정이 곧 제출이고(DEC-14) 확정은 요구사항을 만들지 않는다
 * (GH-139). 그래서 요구사항 0건은 막지 않는다. SW설계서처럼 요구사항 표가 없는 문서도 낸다.
 */
export function missingForSubmit(draft: { type: string; title: string; version: string }): string[] {
  const missing: string[] = [];
  if (!draft.type) missing.push('유형');
  if (!draft.title.trim()) missing.push('제목');
  if (!draft.version.trim()) missing.push('버전');
  return missing;
}
