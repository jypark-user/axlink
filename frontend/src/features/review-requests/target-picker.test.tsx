import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TargetPicker } from '@/features/review-requests/target-picker';

// 확인 요청 대상 고르기(11-18). 항목이 많으면 찾아서 고른다.

const targets = [
  { key: 'a', label: '1.1 착수보고' },
  { key: 'b', label: '1.2 범위·평가기준 합의' },
  { key: 'c', label: '2.3 표준 데이터 모델 적재' },
];

describe('대상 고르기', () => {
  it('띄어쓰기와 상관없이 찾는다', () => {
    render(<TargetPicker targets={targets} value="" onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('대상 찾기'), { target: { value: '1.2범위' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('여러 낱말은 모두 들어간 항목만 남긴다', () => {
    render(<TargetPicker targets={targets} value="" onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('대상 찾기'), { target: { value: '데이터 적재' } });
    expect(screen.getByRole('option')).toHaveTextContent('2.3 표준 데이터 모델 적재');
  });

  it('누르면 고르고, 하나 남았을 때 Enter 로도 고른다', () => {
    const onChange = vi.fn();
    render(<TargetPicker targets={targets} value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole('option', { name: '1.1 착수보고' }));
    expect(onChange).toHaveBeenLastCalledWith('a');
    const box = screen.getByLabelText('대상 찾기');
    fireEvent.change(box, { target: { value: '적재' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('c');
  });

  it('고른 대상을 표시한다', () => {
    render(<TargetPicker targets={targets} value="b" onChange={() => {}} />);
    expect(screen.getByRole('option', { name: '1.2 범위·평가기준 합의' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
