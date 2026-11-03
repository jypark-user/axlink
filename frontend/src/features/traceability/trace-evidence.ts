/**
 * 추적 연결의 근거 표시 (SWFR.PIP.004). 연결마다 어디서 읽어 냈는지(근거 유형)와 원문 위치를
 * 사람 말로 적는다. 값은 서버가 저장한 것만 잇고 화면이 보태지 않는다.
 */

/** 근거 유형(trace_link.evidence_kind). 어디서 이 연결을 읽어 냈는지 사람 말로 적는다 (SWFR.PIP.004). */
export const EVIDENCE_KIND_TEXT: Record<string, string> = {
  TEXT_REQ_CODE: '커밋·이슈 본문의 요구사항 코드',
  TEXT_ISSUE_REF: '커밋·이슈 본문의 이슈 참조',
  TEXT_FILE_PATH: '커밋이 바꾼 파일 경로',
  CUSTOM_FIELD: '이슈 도구의 REQ ID 필드',
  ISSUE_RELATION: '이슈 도구의 이슈 관계',
  DOC_REQ_REF: '저장소 설계 문서의 요구사항 참조',
};

interface EvidenceMeta {
  path?: string | null;
  line?: number | null;
  section?: string | null;
  commitSha?: string | null;
  docStatusText?: string | null;
  qualifier?: string | null;
}

/** 근거 원문의 위치. 설계 문서 참조는 경로·줄·절이 함께 저장된다(ARC-024). 다른 근거는 링크 하나다. */
export function evidenceLocation(meta: Record<string, unknown> | null | undefined): string | null {
  const m = (meta ?? {}) as EvidenceMeta;
  const parts: string[] = [];
  if (m.path) parts.push(m.path);
  if (typeof m.line === 'number') parts.push(`${m.line}줄`);
  if (m.section) parts.push(m.section);
  if (m.commitSha) parts.push(`커밋 ${m.commitSha.slice(0, 7)}`);
  if (m.docStatusText) parts.push(`문서 상태 ${m.docStatusText}`);
  if (m.qualifier) parts.push(m.qualifier);
  return parts.length > 0 ? parts.join(' · ') : null;
}
