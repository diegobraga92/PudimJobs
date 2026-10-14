import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { CVStructure, MasterCV } from '../../services/cv.service';
import { I18nService } from '../../services/i18n.service';
import { CvEditorComponent } from './cv-editor.component';

const STRUCTURED: CVStructure = {
  full_name: 'Ada Lovelace',
  email: 'ada@example.com',
  phone: '+351 900 000 000',
  location: 'Lisbon, PT',
  links: ['https://github.com/ada'],
  summary: 'Backend engineer focused on async Python services.',
  experience: [
    {
      company: 'Acme',
      title: 'Python Developer',
      start_date: '2021-01',
      end_date: null,
      bullets: ['Cut p95 latency 40%.'],
    },
  ],
  education: [{ institution: 'MIT', degree: 'BSc Computer Science', year: '2016' }],
  skills: ['python', 'fastapi'],
  projects: [],
  certifications: ['AWS Solutions Architect'],
  languages: ['English'],
};

const MASTER_CV: MasterCV = {
  id: 'cv-1',
  label: 'v1',
  version: 1,
  is_current: true,
  structured_json: STRUCTURED,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

async function setup(): Promise<{
  fixture: ComponentFixture<CvEditorComponent>;
  component: CvEditorComponent;
  http: HttpTestingController;
}> {
  const builder = TestBed.configureTestingModule({
    imports: [CvEditorComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  await builder.compileComponents();

  const fixture = TestBed.createComponent(CvEditorComponent);
  const component = fixture.componentInstance;
  TestBed.inject(I18nService).setLanguage('en');
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  return { fixture, component, http };
}

describe('CvEditorComponent', () => {
  let component: CvEditorComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    ({ component, http } = await setup());
  });

  afterEach(() => http.verify());

  it('pre-fills the editor from the current master CV (contact + certifications)', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);

    expect(component.cvForm.value.fullName).toBe('Ada Lovelace');
    expect(component.cvForm.value.contactEmail).toBe('ada@example.com');
    expect(component.cvForm.value.location).toBe('Lisbon, PT');
    expect(component.cvForm.value.linksText).toBe('https://github.com/ada');
    expect(component.cvForm.value.certificationsText).toBe('AWS Solutions Architect');
    expect(component.cvForm.value.languagesText).toBe('English');
    expect(component.displayName).toBe('Ada Lovelace');
  });

  it('does not touch the tailored-CV endpoints any more', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);

    http.expectNone('/api/cv/generated');
    // The editor holds the master document, not a per-job tailored version.
    expect(component.cvForm.value.summary).toBe(STRUCTURED.summary);
    expect(component.mode).toBe('edit');
  });

  it('parses ODT uploads and rejects other extensions', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);

    const odt = fileInput('cv.odt');
    component.onFileSelected({ target: odt } as unknown as Event);
    http.expectOne('/api/cv/parse').flush({ ...STRUCTURED, summary: 'From ODT' });
    expect(component.cvForm.value.summary).toBe('From ODT');

    component.onFileSelected({ target: fileInput('cv.txt') } as unknown as Event);
    http.expectNone('/api/cv/parse');
    expect(component.error).toBe(component.i18n.t('errors.unsupportedCvFile'));
  });

  it('exports the current CV with the selected template', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);

    component.exportCv('pdf', 'ats');

    const request = http.expectOne(
      (candidate) => candidate.url === '/api/cv/pdf' && candidate.params.get('template') === 'ats'
    );
    expect(request.request.params.get('format')).toBe('pdf');
    expect(request.request.responseType).toBe('blob');
    request.flush(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));

    expect(component.exporting).toBeFalse();
  });

  it('exports the current CV as DOCX for the Word download', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);

    component.exportCv('docx');
    http.expectOne(
      (candidate) => candidate.url === '/api/cv/pdf' && candidate.params.get('format') === 'docx'
    );

    expect(component.exporting).toBeTrue();
  });
});

describe('CvEditorComponent (master CV only)', () => {
  let component: CvEditorComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    ({ component, http } = await setup());
  });

  afterEach(() => http.verify());

  it('never loads a tailored CV, even when ?generated= is present', () => {
    // ADR 016: tailoring is separated from the master document, so no code path
    // here touches `/api/cv/generated`.
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);
    http.expectNone('/api/cv/generated');

    expect(component.cvForm.value.summary).toBe(STRUCTURED.summary);
    expect(component.mode).toBe('edit');
  });
});

/** Build a change event-ish input element carrying a single file. */
function fileInput(name: string): HTMLInputElement {
  const input = document.createElement('input');
  Object.defineProperty(input, 'files', { value: [new File(['x'], name)] });
  return input;
}
