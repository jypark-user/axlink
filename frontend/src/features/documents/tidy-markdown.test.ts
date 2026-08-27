import { describe, expect, it } from 'vitest';
import { tidyMarkdown } from '@/features/documents/tidy-markdown';

describe('tidyMarkdown', () => {
  it('제목을 세우고 글머리표는 목록으로, 번호는 번호대로 둔다', () => {
    const raw = [
      '제 1 장 사업 개요',
      '- 12 -',
      '본 사업은 발주사가 다수의 SI 사업을',
      '한눈에 감독할 수 있도록 하는 것을 목적으로 한다.',
      '',
      '1.1 추진 배경',
      '• 산출물 검토가 수작업이다',
      '(2) 진행 상황을 모아 볼 자리가 없다',
    ].join('\n');

    expect(tidyMarkdown(raw)).toBe(
      [
        '## 제 1 장 사업 개요',
        '',
        '본 사업은 발주사가 다수의 SI 사업을 한눈에 감독할 수 있도록 하는 것을 목적으로 한다.',
        '',
        '### 1.1 추진 배경',
        '',
        '- 산출물 검토가 수작업이다',
        '2. 진행 상황을 모아 볼 자리가 없다',
      ].join('\n'),
    );
  });

  it('문장으로 이어지는 번호는 제목이 아니라 번호 목록이다', () => {
    const raw = ['1. 수급인은 착수계를 제출하여야 한다.', '2. 발주사는 이를 검토한다.'].join('\n');
    expect(tidyMarkdown(raw)).toBe(raw);
  });
});

describe('tidyMarkdown · 줄바꿈을 잃은 글', () => {
  const run = [
    '제 안 요 청 서 사업명 전라남도 주거복지포털 시스템 구축 주관기관 전남개발공사 2025. 2.',
    '목 차 I. 사업안내 1. 사업개요 ……………………………………… 1 2. 추진배경 및 필요성',
    '…………………… 1 3. 사업범위 ……………………………… 1 4. 시스템구성도(안) ……… 2',
    'Ⅲ. 제안요청 사항 2.1 상세요구사항 …………………………………… 7',
    '본 사업은 주거복지 정보를 한곳에서 제공한다. 이를 위하여 포털을 새로 구축한다.',
  ].join(' ');

  const lines = tidyMarkdown(run).split('\n').filter(Boolean);

  it('목차를 번호 목록으로 편다', () => {
    expect(lines).toContain('1. 사업개요');
    expect(lines).toContain('2. 추진배경 및 필요성');
    expect(lines).toContain('4. 시스템구성도(안)');
    // 2.1 은 2번 아래 1번 — 들여쓴 번호로 둔다
    expect(lines).toContain('   1. 상세요구사항');
  });

  it('채움 문자·쪽 번호를 걷어 내고 벌어진 자간을 붙인다', () => {
    expect(lines.join('\n')).not.toMatch(/[.·…]{3}/);
    expect(lines).not.toContain('1');
    expect(lines[0]).toMatch(/^제안요청서 /);
  });

  it('큰 제목에서 끊고 문장을 줄로 나눈다', () => {
    expect(lines).toContain('## 목차');
    expect(lines).toContain('## I. 사업안내');
    expect(lines).toContain('## Ⅲ. 제안요청 사항');
    expect(lines).toContain('본 사업은 주거복지 정보를 한곳에서 제공한다.');
    expect(lines).toContain('이를 위하여 포털을 새로 구축한다.');
  });
});

describe('tidyMarkdown · 표와 안 보이는 글자', () => {
  it('칸이 나뉜 줄이 이어지면 표로 짠다', () => {
    const raw = [
      '구분\t담당\t연락처',
      '과업관련\t김완수\t061)280-0443',
      '계약관련\t강동훈\t061)280-0623',
    ].join('\n');

    expect(tidyMarkdown(raw)).toBe(
      [
        '| 구분 | 담당 | 연락처 |',
        '| --- | --- | --- |',
        '| 과업관련 | 김완수 | 061)280-0443 |',
        '| 계약관련 | 강동훈 | 061)280-0623 |',
      ].join('\n'),
    );
  });

  it('한 줄뿐이면 표로 보지 않는다', () => {
    expect(tidyMarkdown('사업명    전라남도 주거복지포털')).toBe('사업명 전라남도 주거복지포털');
  });

  it('제어 문자·깨진 글자·폭 없는 공백을 지운다', () => {
    expect(tidyMarkdown('사업\u0001개요\ufffd\u200b\ue0a0 시작')).toBe('사업개요 시작');
  });
});

describe('tidyMarkdown · 요구사항 카드', () => {
  it('이름표가 줄로 쪼개져 와도 카드로 선다', () => {
    const raw = [
      '요구사항고유번호 SFR-003 요구사항 명칭 전자정부 표준프레임워크 적용 요구사항 분류 기능 요구사항 요구',
      '사항',
      '상세',
      '설명 정의 전자정부 표준프레임워크 기반 개발 세부',
      '내용 ❍ 표준프레임워크 4.0 이상 적용 ❍ 호환성 인증 필요 산출정보 호환성 인증서',
    ].join('\n');

    expect(tidyMarkdown(raw).split('\n').filter(Boolean)).toEqual([
      '### SFR-003 전자정부 표준프레임워크 적용',
      '**요구사항 분류** 기능 요구사항',
      '**요구 사항 상세 설명** 정의 전자정부 표준프레임워크 기반 개발',
      '**세부 내용**',
      '- 표준프레임워크 4.0 이상 적용',
      '- 호환성 인증 필요',
      '**산출정보** 호환성 인증서',
    ]);
  });

  it('첨부 서식 목록은 버린다', () => {
    const raw = [
      '[별지 1호 서식] (정량) 제안서 표지',
      '[별지 3호 서식] 입찰참가신청서',
      '본문은 남는다.',
    ].join('\n');

    expect(tidyMarkdown(raw)).toBe('본문은 남는다.');
  });
});
