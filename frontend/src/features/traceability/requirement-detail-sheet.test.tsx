import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { RequirementDetailSheet } from '@/features/traceability/requirement-detail-sheet';
import { evidenceLocation } from '@/features/traceability/trace-evidence';
import type { RequirementDetailResponse } from '@/types/api';

// 요구사항 상세(GH-158). 확정 명세서의 원문 위치, 끊긴 연결의 사유, 변경 이력이 화면에 보여야 한다.
// 10-30 검증에서는 이 내용을 API 로만 확인할 수 있었다.

const detail = {
  id: 'r1',
  projectId: 'p1',
  code: 'SWFR.CON.001',
  title: '커넥터는 공통 인터페이스를 구현한다',
  priority: 'MUST',
  status: 'DEFINED',
  assignee: null,
  source: { tool: 'UPLOAD', connectionId: null, externalId: null, externalUrl: null },
  traceComplete: false,
  updatedAt: '2026-10-29T08:08:39Z',
  statusBasis: null,
  evidenceStatus: 'DEFINED',
  decision: null,
  inBaseline: true,
  body: '커넥터는 공통 인터페이스를 구현하며, 신규 도구 연동이 구현체 추가만으로 가능해야 한다',
  traceLinks: [
    {
      id: 'l1',
      projectId: 'p1',
      fromType: 'CODE_CHANGE',
      fromId: 'c1',
      fromLabel: 'abc1234 커넥터 포트',
      toType: 'REQUIREMENT',
      toId: 'r1',
      toLabel: 'SWFR.CON.001',
      linkKind: 'IMPLEMENTS',
      origin: 'AUTO',
      status: 'BROKEN',
      evidenceKind: 'COMMIT_MESSAGE',
      evidenceText: 'feat: 커넥터 포트 [SWFR.CON.001]',
      externalUrl: 'https://github.com/o/r/commit/abc1234',
      createdAt: '2026-10-29T08:00:00Z',
      statusReason: '커밋 메시지가 바뀌어 근거가 사라졌다',
    },
    {
      id: 'l2',
      projectId: 'p1',
      fromType: 'REPO_DOCUMENT',
      fromId: 'doc1',
      fromLabel: 'ARC-004',
      toType: 'REQUIREMENT',
      toId: 'r1',
      toLabel: 'SWFR.CON.001',
      linkKind: 'DESIGNS',
      origin: 'AUTO',
      status: 'ACTIVE',
      evidenceKind: 'DOC_REQ_REF',
      evidenceText: '| SWFR.CON.001 | 포트 인터페이스 | 4.1 |',
      externalUrl: 'https://github.com/o/r/blob/abc1234def/docs/20-design/ARC-004.md#L88',
      createdAt: '2026-10-29T08:00:00Z',
      evidenceMeta: {
        path: 'docs/20-design/ARC-004.md',
        line: 88,
        section: '9. 대응표',
        commitSha: 'abc1234def5678',
        docStatusText: '확정',
      },
    },
    {
      id: 'l3',
      projectId: 'p1',
      fromType: 'ISSUE',
      fromId: 'i1',
      fromLabel: 'GH-77 수기 연결 이슈',
      toType: 'REQUIREMENT',
      toId: 'r1',
      toLabel: 'SWFR.CON.001',
      linkKind: 'IMPLEMENTS',
      origin: 'MANUAL',
      status: 'ACTIVE',
      evidenceKind: null,
      evidenceText: null,
      externalUrl: null,
      createdAt: '2026-10-29T08:00:00Z',
    },
  ],
  history: [
    {
      id: 'h1',
      entityType: 'REQUIREMENT',
      entityId: 'r1',
      field: 'baseline',
      fromValue: null,
      toValue: 'v1 NEW',
      actor: '진흥원 사업담당',
      actorName: null,
      changedAt: '2026-10-29T08:08:39Z',
    },
  ],
  baselineSource: {
    baselineId: 'b1',
    version: 1,
    status: 'CONFIRMED',
    confirmedAt: '2026-10-29T08:08:39Z',
    confirmedBy: '진흥원 사업담당',
    documentId: 'd1',
    sourceFilename: 'IM-001-요구사항정의서_v1.0.docx',
    sourceDocVersion: '1.0',
    location: '표 3 · 2행',
    match: 'NEW',
  },
} as unknown as RequirementDetailResponse;

const get = vi.fn((_path: string) => Promise.resolve(detail));
vi.mock('@/lib/http', () => ({ api: { get: (path: string) => get(path) } }));

describe('요구사항 상세', () => {
  it('확정 명세서의 판본·원문 위치와 문서 링크를 보인다', async () => {
    render(
      <MemoryRouter>
        <RequirementDetailSheet projectId="p1" requirementId="r1" onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('표 3 · 2행')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/projects/p1/requirements/r1');
    const doc = screen.getByRole('link', { name: 'IM-001-요구사항정의서_v1.0.docx' });
    expect(doc).toHaveAttribute('href', '/p/p1/documents/d1');
    expect(screen.getByText(/문서 판본 1.0/)).toBeInTheDocument();
  });

  it('끊긴 연결은 상태와 사유를, 이력은 확정 판정을 사람 말로 보인다', async () => {
    render(
      <MemoryRouter>
        <RequirementDetailSheet projectId="p1" requirementId="r1" onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/근거 사라짐/)).toBeInTheDocument();
    expect(screen.getByText(/커밋 메시지가 바뀌어 근거가 사라졌다/)).toBeInTheDocument();
    expect(screen.getByText(/v1 \(새로 들어옴\)/)).toBeInTheDocument();
  });

  // 연결마다 근거 유형과 원문 위치가 보여야 사람이 확인할 수 있다 (SWFR.PIP.004)
  it('연결마다 근거 유형과 원문 위치를 보인다. 수기 연결은 그렇게 적는다', async () => {
    render(
      <MemoryRouter>
        <RequirementDetailSheet projectId="p1" requirementId="r1" onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/저장소 설계 문서의 요구사항 참조/)).toBeInTheDocument();
    expect(
      screen.getByText(
        /docs\/20-design\/ARC-004.md · 88줄 · 9. 대응표 · 커밋 abc1234 · 문서 상태 확정/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/사람이 직접 이음/)).toBeInTheDocument();
    // 알지 못하는 유형은 숨기지 않고 그대로 적는다
    expect(screen.getByText(/COMMIT_MESSAGE/)).toBeInTheDocument();
    const doc = screen.getByRole('link', { name: /ARC-004/ });
    expect(doc).toHaveAttribute('href', expect.stringContaining('#L88'));
  });

  it('원문 위치는 저장된 값만 잇고 없으면 null 이다', () => {
    expect(evidenceLocation(null)).toBeNull();
    expect(evidenceLocation({})).toBeNull();
    expect(evidenceLocation({ path: 'a.md', line: 3 })).toBe('a.md · 3줄');
  });

  it('닫혀 있으면 불러오지 않는다', () => {
    get.mockClear();
    render(
      <MemoryRouter>
        <RequirementDetailSheet projectId="p1" requirementId={null} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(get).not.toHaveBeenCalled();
  });
});
