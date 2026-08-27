import { useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { fieldErrorMap, isApiError } from '@/lib/api-error';
import type { ProjectCreateRequest } from '@/types/api';

export type ProjectFormValues = ProjectCreateRequest;

export const EMPTY_PROJECT: ProjectFormValues = {
  name: '',
  startDate: '',
  endDate: '',
  description: '',
  contractorName: '',
  deletePassword: '',
};

export function validateProject(
  values: ProjectFormValues,
  requireDeletePassword = false,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.name.trim()) errors.name = '사업명을 입력하세요.';
  if (!values.startDate) errors.startDate = '착수일을 입력하세요.';
  if (!values.endDate) errors.endDate = '마감일을 입력하세요.';
  if (!values.description.trim()) errors.description = '설명을 입력하세요.';
  if (values.startDate && values.endDate && values.startDate > values.endDate) {
    errors.endDate = '마감일은 착수일보다 빠를 수 없습니다.';
  }
  if (requireDeletePassword && values.deletePassword.trim().length < 4) {
    errors.deletePassword = '삭제 비밀번호를 4자 이상으로 정하세요.';
  }
  return errors;
}

export function ProjectForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  requireDeletePassword = false,
  children,
}: {
  initial?: ProjectFormValues;
  submitLabel: string;
  onSubmit: (values: ProjectFormValues) => Promise<void>;
  onCancel?: () => void;
  /** 사업을 지울 때 맞출 비밀번호를 여기서 정한다 — 등록에서만 쓴다. */
  requireDeletePassword?: boolean;
  /** 기본 정보 아래에 덧붙는 칸 — 사업 등록에서 첨부 파일이 여기 들어간다. */
  children?: ReactNode;
}): ReactNode {
  const [values, setValues] = useState<ProjectFormValues>(initial ?? EMPTY_PROJECT);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const set = (key: keyof ProjectFormValues, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const next = validateProject(values, requireDeletePassword);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setPending(true);
    try {
      await onSubmit(values);
    } catch (err) {
      const mapped = fieldErrorMap(err);
      setErrors(mapped);
      if (Object.keys(mapped).length === 0) {
        setFormError(isApiError(err) ? err.message : '저장에 실패했습니다.');
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="flex max-w-2xl flex-col gap-4">
      {formError && <p className="text-sm text-destructive">{formError}</p>}
      <Field id="name" label="사업명" error={errors.name}>
        <Input id="name" value={values.name} onChange={(e) => set('name', e.target.value)} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="startDate" label="착수일" error={errors.startDate}>
          <Input
            id="startDate"
            type="date"
            value={values.startDate}
            onChange={(e) => set('startDate', e.target.value)}
          />
        </Field>
        <Field id="endDate" label="마감일" error={errors.endDate}>
          <Input
            id="endDate"
            type="date"
            value={values.endDate}
            onChange={(e) => set('endDate', e.target.value)}
          />
        </Field>
      </div>
      <Field id="contractorName" label="용역사" error={errors.contractorName}>
        <Input
          id="contractorName"
          autoComplete="off"
          placeholder="이 사업을 맡을 용역사"
          value={values.contractorName}
          onChange={(e) => set('contractorName', e.target.value)}
        />
      </Field>
      <Field id="description" label="설명" error={errors.description}>
        <Textarea
          id="description"
          rows={4}
          value={values.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </Field>
      {requireDeletePassword && (
        <Field id="deletePassword" label="삭제 비밀번호" error={errors.deletePassword}>
          <Input
            id="deletePassword"
            type="password"
            autoComplete="new-password"
            value={values.deletePassword}
            onChange={(e) => set('deletePassword', e.target.value)}
          />
          <p className="text-muted-foreground text-sm">
            이 사업을 지울 때 맞춰야 합니다. 잊으면 지울 수 없습니다.
          </p>
        </Field>
      )}

      {children}

      <div className="flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? '저장 중…' : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            취소
          </Button>
        )}
      </div>
    </form>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}): ReactNode {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
