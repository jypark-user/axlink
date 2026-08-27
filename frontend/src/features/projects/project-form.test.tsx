import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ProjectForm, validateProject } from '@/features/projects/project-form';
import { ApiError } from '@/lib/api-error';

describe('validateProject', () => {
  it('rejects missing required fields', () => {
    const errors = validateProject({
      name: '',
      startDate: '',
      endDate: '',
      description: '',
      contractorName: '',
      deletePassword: '',
    });
    expect(Object.keys(errors).sort()).toEqual(['description', 'endDate', 'name', 'startDate']);
  });

  it('rejects an end date before the start date', () => {
    const errors = validateProject({
      name: '차세대',
      startDate: '2026-03-01',
      endDate: '2026-02-28',
      description: '설명',
      contractorName: '',
      deletePassword: '',
    });
    expect(errors.endDate).toBe('마감일은 착수일보다 빠를 수 없습니다.');
  });

  it('accepts an end date equal to the start date', () => {
    const errors = validateProject({
      name: '차세대',
      startDate: '2026-03-01',
      endDate: '2026-03-01',
      description: '설명',
      contractorName: '',
      deletePassword: '',
    });
    expect(errors).toEqual({});
  });
});

describe('ProjectForm', () => {
  it('blocks submit and shows field messages when required fields are empty', async () => {
    const onSubmit = vi.fn();
    render(<ProjectForm submitLabel="생성" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findAllByRole('alert')).toHaveLength(4);
  });

  it('maps server fieldErrors onto the matching field', async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiError(400, 'VALIDATION_FAILED', '입력값이 올바르지 않습니다.', {
        fieldErrors: [{ field: 'name', reason: '이미 존재하는 이름입니다.' }],
      }),
    );
    render(
      <ProjectForm
        submitLabel="생성"
        initial={{
          name: '차세대',
          startDate: '2026-03-01',
          endDate: '2026-12-31',
          description: '설명',
          contractorName: '',
          deletePassword: '',
        }}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: '차세대',
      startDate: '2026-03-01',
      endDate: '2026-12-31',
      description: '설명',
      contractorName: '',
      deletePassword: '',
    });
    expect(await screen.findByText('이미 존재하는 이름입니다.')).toBeInTheDocument();
  });
});
