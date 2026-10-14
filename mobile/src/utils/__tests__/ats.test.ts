import { AtsReport } from '@/types';
import { deterministicScore, factorPercent, scoreVariant } from '@/utils/ats';

describe('scoreVariant', () => {
  it('bands the badge tone by score', () => {
    expect(scoreVariant(82)).toBe('success');
    expect(scoreVariant(75)).toBe('success');
    expect(scoreVariant(74)).toBe('warning');
    expect(scoreVariant(50)).toBe('warning');
    expect(scoreVariant(49)).toBe('danger');
    expect(scoreVariant(0)).toBe('danger');
  });
});

describe('factorPercent', () => {
  it('scales a 0..1 factor score to a bar width', () => {
    expect(factorPercent(0.8)).toBe(80);
    expect(factorPercent(0.005)).toBe(1);
    expect(factorPercent(0)).toBe(0);
  });

  it('clamps out-of-range input', () => {
    expect(factorPercent(2)).toBe(100);
    expect(factorPercent(-1)).toBe(0);
  });
});

describe('deterministicScore', () => {
  const report = (overrides: Partial<AtsReport> = {}): AtsReport => ({
    score: 82,
    method: 'heuristic',
    factors: [],
    matched_skills: [],
    missing_skills: [],
    recommendations: [],
    warnings: [],
    llm_summary: null,
    ...overrides,
  });

  it('prefers the deterministic baseline over the AI estimate', () => {
    expect(deterministicScore(report({ deterministic_score: 70, llm_score: 30 }))).toBe(70);
  });

  it('falls back to `score` for a report cached before deterministic_score existed', () => {
    expect(deterministicScore(report())).toBe(82);
  });
});
