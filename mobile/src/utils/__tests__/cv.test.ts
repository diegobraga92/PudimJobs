import { CVStructure, GeneratedCV } from '@/types';
import { hasContent, variantLabelKey } from '@/utils/cv';

const STRUCTURE: CVStructure = {
  summary: 'Tailored for Acme.',
  experience: [],
  education: [],
  skills: ['python'],
  projects: [],
};

function artifact(overrides: Partial<GeneratedCV> = {}): GeneratedCV {
  return {
    id: 'gen-1',
    job_id: 'job-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    source_master_cv_id: 'cv-master-1',
    variant: 'rule',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    structured_json: STRUCTURE,
    ats_score: null,
    ats_report: null,
    ...overrides,
  };
}

describe('cv variant helpers', () => {
  it('maps each production variant to its dictionary key (ADR 016)', () => {
    expect(variantLabelKey('rule')).toBe('cv.variant.rule');
    expect(variantLabelKey('llm')).toBe('cv.variant.llm');
  });
});

describe('hasContent', () => {
  it('accepts an artifact that carries its own CV content', () => {
    expect(hasContent(artifact())).toBe(true);
  });

  it('rejects a legacy artifact left without content (ADR 016)', () => {
    // A pre-ADR-016 row has nothing to preview, edit or score: it is not a CV,
    // so the panel must show the empty state instead of a card behind it.
    expect(hasContent(artifact({ structured_json: null }))).toBe(false);
  });
});
