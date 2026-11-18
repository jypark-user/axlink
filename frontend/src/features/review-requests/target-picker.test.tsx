import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TargetPicker } from '@/features/review-requests/target-picker';

// 확인 요청 대상 고르기(11-18). 누르면 펼쳐지고 검색해서 고른다.

const targets = [
  { key: 'a', label: '1.1 착수보고' },
  { key: 'b', label: '1.2 범위·평가기준 합의' },
  { key: 'c', label: '2.3 표준 데이터 모델 적재' },
];

function openPicker(): HTMLElement {
  fireEvent.click(screen.getByRole('combobox'));
  return screen.getByLabelText('대상 찾기');
}

describe('대상 고르기', () => {
  it('고른 대상이 없으면 안내 문구를, 있으면 그 이름을 보인다', () => {
    const { rerender } = render(<TargetPicker targets={targets} value="" onChange={() => {}} />);
    expect(screen.getByRole('combobox')).toHaveTextContent('대상을 고르세요');
    rerender(<TargetPicker targets={targets} value="b" onChange={() => {}} />);
    expect(screen.getByRole('combobox')).toHaveTextContent('1.2 범위·평가기준 합의');
  });

  it('띄어쓰기와 상관없이 찾는다', () => {
    render(<TargetPicker targets={targets} value="" onChange={() => {}} />);
    fireEvent.change(openPicker(), { target: { value: '1.2범위' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('여러 낱말은 모두 들어간 항목만 남긴다', () => {
    render(<TargetPicker targets={targets} value="" onChange={() => {}} />);
    fireEvent.change(openPicker(), { target: { value: '데이터 적재' } });
    expect(screen.getByRole('option')).toHaveTextContent('2.3 표준 데이터 모델 적재');
  });

  it('누르거나 화살표·Enter 로 고른다', () => {
    const onChange = vi.fn();
    render(<TargetPicker targets={targets} value="" onChange={onChange} />);
    openPicker();
    fireEvent.click(screen.getByRole('option', { name: '1.1 착수보고' }));
    expect(onChange).toHaveBeenLastCalledWith('a');
    const box = openPicker();
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('b');
  });

  it('대상이 없으면 누를 수 없다', () => {
    render(<TargetPicker targets={[]} value="" onChange={() => {}} />);
    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(screen.getByRole('combobox')).toHaveTextContent('대상이 없습니다');
  });
});
