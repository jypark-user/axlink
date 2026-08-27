export const MAX_BYTES = 50 * 1024 * 1024;
export const ALLOWED = ['.pdf', '.docx', '.xlsx', '.pptx', '.hwp', '.hwpx', '.md', '.txt'];

/** 올릴 수 없는 파일이면 사유, 올릴 수 있으면 null. 문서 화면과 사업 등록이 같은 규칙을 쓴다. */
export function rejectReason(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!ALLOWED.includes(ext)) return `지원하지 않는 형식입니다 (${ALLOWED.join(', ')})`;
  if (file.size > MAX_BYTES) return '50MB 이하 파일만 업로드할 수 있습니다.';
  return null;
}
