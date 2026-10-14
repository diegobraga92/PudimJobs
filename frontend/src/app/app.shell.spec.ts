import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';

import { routes } from './app.routes';
import { LayoutComponent } from './components/layout/layout.component';
import { DICTIONARY, I18nService } from './services/i18n.service';

describe('App shell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LayoutComponent],
      providers: [provideRouter([]), provideHttpClient()],
    }).compileComponents();
  });

  it('exposes every feature route behind the auth guard', () => {
    const shell = routes.find((route) => route.path === '');
    const paths = (shell?.children ?? []).map((route) => route.path);

    expect(paths).toContain('jobs');
    expect(paths).toContain('sources');
    expect(paths).toContain('cv');
    expect(paths).toContain('applications');
    expect(paths).toContain('lessons');
    expect(paths).toContain('prep-tasks');
    expect(shell?.canActivate).toContain(jasmine.any(Function));
  });

  it('links the data-driven pages from the sidebar', () => {
    const layout = TestBed.createComponent(LayoutComponent).componentInstance;
    const navRoutes = layout.navItems.map((item) => item.route);

    expect(navRoutes).toContain('/cv');
    expect(navRoutes).toContain('/applications');
    expect(navRoutes).toContain('/prep-tasks');
    expect(navRoutes).toContain('/lessons');
  });
});

describe('I18nService', () => {
  const service = new I18nService();

  afterEach(() => service.setLanguage('en'));

  it('translates every dictionary entry in both languages', () => {
    const untranslated = Object.entries(DICTIONARY)
      .filter(([, entry]) => !entry.en.trim() || !entry['pt-BR'].trim())
      .map(([key]) => key);

    expect(untranslated).toEqual([]);
  });

  it('covers the strings of every user-facing workspace', () => {
    for (const key of [
      'layout.nav.prepTasks',
      'layout.nav.lessons',
      'cv.contact',
      'cv.certifications',
      'cv.template.ats',
      'cv.format.docx',
      'cv.docxExported',
      'errors.failedExportDocx',
      'errors.failedDownloadDocx',
      'cv.ats.title',
      'prepTasks.title',
      'prepTasks.status.in_progress',
      'prepTasks.category.behavioral',
      'lessons.title',
      'applications.lessonsLearned',
    ]) {
      expect(DICTIONARY[key]).withContext(key).toBeDefined();
    }
  });

  it('interpolates parameters and falls back to the key', () => {
    expect(service.t('cv.ats.scoreBadge', { score: 91 })).toBe('91/100');
    expect(service.t('does.not.exist')).toBe('does.not.exist');
  });
});
