import { CVStructure, GeneratedCV } from '@/types';
import { defaultArtifact, cvFileStem, hasContent, variantLabelKey } from '@/utils/cv';

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
    file_stem: 'Ada-Lovelace-CV-Backend-Engineer',
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

describe('defaultArtifact', () => {
  const rule = artifact();
  const llm = artifact({ id: 'gen-2', variant: 'llm' });

  it('opens on the AI rewrite when nothing was recorded as sent (ADR 029)', () => {
    expect(defaultArtifact([rule, llm], null)?.id).toBe('gen-2');
  });

  it('keeps the recorded choice even when the AI rewrite is listed first', () => {
    expect(defaultArtifact([llm, rule], 'gen-1')?.id).toBe('gen-1');
  });

  it('falls back to the first artifact when only the fallback exists', () => {
    expect(defaultArtifact([rule], null)?.id).toBe('gen-1');
  });

  it('ignores a recorded id that is no longer in the list', () => {
    expect(defaultArtifact([rule], 'gen-deleted')?.id).toBe('gen-1');
  });

  it('has nothing to open on an empty list', () => {
    expect(defaultArtifact([], 'gen-1')).toBeNull();
  });
});

describe('cvFileStem (ADR 030)', () => {
  it('names the candidate and the document, in that order', () => {
    expect(cvFileStem('Ada Lovelace')).toBe('Ada-Lovelace-CV');
  });

  it('strips accents so a share sheet cannot mangle the name', () => {
    expect(cvFileStem('José Conceição')).toBe('Jose-Conceicao-CV');
  });

  it('drops parentheticals and punctuation', () => {
    expect(cvFileStem('Ada Lovelace (Remote)!!')).toBe('Ada-Lovelace-CV');
  });

  it('falls back to the bare document when there is no name', () => {
    expect(cvFileStem('')).toBe('CV');
    expect(cvFileStem(null)).toBe('CV');
    expect(cvFileStem(undefined)).toBe('CV');
  });

  it('never doubles the document type for a junk name', () => {
    expect(cvFileStem('Curriculum Vitae')).toBe('CV');
    expect(cvFileStem('Resume')).toBe('CV');
  });

  it('caps a long name on a word boundary', () => {
    const stem = cvFileStem('Maximiliano de Albuquerque Nascimento Filho Sobrinho');
    expect(stem.endsWith('-CV')).toBe(true);
    expect(stem.length).toBeLessThanOrEqual(48 + '-CV'.length);
  });
});
