/**
 * Shared fixtures for StandardEditor.*.test.jsx siblings.
 *
 * Split out of StandardEditor.test.jsx. Each test file that imports this
 * module must declare its own `vi.mock(...)` calls for
 * useStandardDetail.js / useStandardsOverrides.js / useAppState.js first
 * (vi.mock hoisting is per-file, so it cannot live here) — then this
 * module's `setup()` picks up the mocked hooks via the same module graph.
 */
import { vi } from 'vitest';
import { useStandardDetail } from '../hooks/useStandardDetail.js';
import { useStandardsOverrides } from '../hooks/useStandardsOverrides.js';
import { useAppState } from '../../../hooks/useAppState.js';

export const MANAGED_STANDARD = {
  id: 'iso-25010',
  name: 'ISO 25010',
  description: 'Quality standard',
  type: 'builtin',
  managed: true,
  principles: [
    {
      name: 'Maintainability',
      description: '',
      requirements: [
        {
          id: 'M-ANA-2',
          text: 'Functions MUST NOT exceed {max_lines} lines',
          description: '',
          refs: [],
          params: { max_lines: { label: 'Max function lines', type: 'int', default: 50, min: 10, max: 500 } },
        },
      ],
    },
  ],
};

// selectedNode pointing at the parameterised requirement so ThresholdFields is rendered
export const REQ_NODE = { type: 'requirement', principleIndex: 0, reqIndex: 0 };

export function makeDetail(extra = {}) {
  return {
    standard: MANAGED_STANDARD,
    loading: false,
    error: null,
    dirty: false,
    editable: false, // managed standard — structure is read-only
    selectedNode: REQ_NODE,
    setSelectedNode: vi.fn(),
    updateField: vi.fn(),
    addPrinciple: vi.fn(),
    removePrinciple: vi.fn(),
    addRequirement: vi.fn(),
    removeRequirement: vi.fn(),
    save: vi.fn().mockResolvedValue(undefined),
    ...extra,
  };
}

export function setup({ projectId = 'proj-1', savedOverrides = {}, previewResult = { changedDimensions: [] } } = {}) {
  const saveOverrides = vi.fn().mockResolvedValue(undefined);
  const previewOverrides = vi.fn().mockResolvedValue(previewResult);
  useAppState.mockReturnValue({ selectedProject: projectId });
  useStandardsOverrides.mockReturnValue({ overrides: savedOverrides, counts: {}, loading: false, error: null, save: saveOverrides, preview: previewOverrides });
  useStandardDetail.mockReturnValue(makeDetail());
  return { saveOverrides, previewOverrides };
}
