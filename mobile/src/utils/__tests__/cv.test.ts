import { variantLabelKey } from '@/utils/cv';

describe('cv variant helpers', () => {
  it('maps each production variant to its dictionary key (ADR 016)', () => {
    expect(variantLabelKey('rule')).toBe('cv.variant.rule');
    expect(variantLabelKey('llm')).toBe('cv.variant.llm');
  });
});
