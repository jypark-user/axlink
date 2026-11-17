import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IssueList, IssueProgressCell } from '@/features/traceability/issue-progress';

// 요구사항에 이어진 이슈·일감의 진행(11-17). 용역사가 얼마나 등록해 얼마나 닫았는지 보인다.

describe('연관 이슈·일감', () => {
  it('닫힘 건수와 전체, 진행·열림을 보인다', () => {
    render(<IssueProgressCell progress={{ total: 4, open: 1, inProgress: 1, closed: 2 }} />);
    expect(screen.getByText(/닫힘/)).toHaveTextContent('닫힘 2 / 4');
    expect(screen.getByText('진행 1 · 열림 1')).toBeInTheDocument();
  });

  it('하나도 없으면 「등록된 이슈 없음」으로 눈에 띄게 보인다', () => {
    render(<IssueProgressCell progress={{ total: 0, open: 0, inProgress: 0, closed: 0 }} />);
    expect(screen.getByText('등록된 이슈 없음')).toBeInTheDocument();
  });

  it('상세 목록은 상태와 결함 표시를 붙인다', () => {
    render(
      <IssueList
        issues={[
          {
            id: 'i1',
            key: 'GH-12',
            title: '로그인 화면',
            status: 'IN_PROGRESS',
            kind: 'GENERAL',
            url: null,
          },
          {
            id: 'i2',
            key: 'RM-3',
            title: '토큰 만료',
            status: 'CLOSED',
            kind: 'DEFECT',
            url: null,
          },
        ]}
      />,
    );
    expect(screen.getByText('진행')).toBeInTheDocument();
    expect(screen.getByText('종료')).toBeInTheDocument();
    expect(screen.getByText('결함')).toBeInTheDocument();
  });
});
