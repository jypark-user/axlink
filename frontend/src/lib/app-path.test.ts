import { describe, expect, it } from 'vitest';
import { apiDownloadPath, appHref } from '@/lib/app-path';

// 시험은 base '/' 로 돈다. /ax-link/ 빌드에서는 같은 함수가 앞에 /ax-link 를 붙인다.
describe('앱 경로', () => {
  it('화면 경로는 앱 경로 아래로, 바깥 주소는 그대로', () => {
    expect(appHref('/p/1/documents')).toBe('/p/1/documents');
    expect(appHref('https://github.com/a/b')).toBe('https://github.com/a/b');
    expect(appHref('//cdn.example/x')).toBe('//cdn.example/x');
  });

  it('API 내려받기 주소만 골라 API 경로로 바꾼다', () => {
    expect(apiDownloadPath('/api/documents/abc/content')).toBe('/documents/abc/content');
    expect(apiDownloadPath('/p/1/documents')).toBeNull();
    expect(apiDownloadPath('https://github.com/a/b')).toBeNull();
    expect(apiDownloadPath(null)).toBeNull();
  });
});
