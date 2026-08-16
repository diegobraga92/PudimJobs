import { DICTIONARY, TranslationEntry } from '@/i18n/dictionary';

describe('i18n dictionary', () => {
  it('contains both locales for every entry', () => {
    for (const [key, entry] of Object.entries<TranslationEntry>(DICTIONARY)) {
      expect(typeof entry.en).toBe('string');
      expect(typeof entry['pt-BR']).toBe('string');
      expect(key).toBeTruthy();
    }
  });

  it('keeps keys dot-namespaced', () => {
    for (const key of Object.keys(DICTIONARY)) {
      expect(key).toMatch(/^[a-z][a-zA-Z0-9.]+$/);
    }
  });

  it('covers the strings used by the mobile shell', () => {
    const required = [
      'login.signIn',
      'login.tagline',
      'layout.nav.jobs',
      'layout.apiOnline',
      'jobs.title',
      'jobDetail.backToJobs',
      'common.description',
      'errors.failedLoadJobs',
    ];
    for (const key of required) {
      expect(DICTIONARY[key]).toBeDefined();
    }
  });
});
