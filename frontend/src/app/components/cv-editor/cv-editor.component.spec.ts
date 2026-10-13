import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { CVStructure, GeneratedCV, MasterCV } from '../../services/cv.service';
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

function tailoredCv(): GeneratedCV {
  return {
    id: 'gen-1',
    master_cv_id: 'cv-1',
    job_id: 'job-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    created_at: '2026-02-01T00:00:00Z',
    structured_json: { ...STRUCTURED, summary: 'Tailored summary', skills: ['python'] },
    ats_score: 61,
    ats_report: null,
  };
}

async function setup(generatedId?: string): Promise<{
  fixture: ComponentFixture<CvEditorComponent>;
  component: CvEditorComponent;
  http: HttpTestingController;
}> {
  const builder = TestBed.configureTestingModule({
    imports: [CvEditorComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  if (generatedId) {
    builder.overrideProvider(ActivatedRoute, {
      useValue: { snapshot: { queryParamMap: convertToParamMap({ generated: generatedId }) } },
    });
  }
  await builder.compileComponents();

  const fixture = TestBed.createComponent(CvEditorComponent);
  const component = fixture.componentInstance;
  TestBed.inject(I18nService).setLanguage('en');
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  return { fixture, component, http };
}

describe('CvEditorComponent', () => {
  let fixture: ComponentFixture<CvEditorComponent>;
  let component: CvEditorComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    ({ fixture, component, http } = await setup());
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

    component.exportPdf('ats');

    const request = http.expectOne(
      (candidate) => candidate.url === '/api/cv/pdf' && candidate.params.get('template') === 'ats'
    );
    expect(request.request.responseType).toBe('blob');
    request.flush(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));

    expect(component.exporting).toBeFalse();
  });
});

describe('CvEditorComponent (tailored deep link)', () => {
  let fixture: ComponentFixture<CvEditorComponent>;
  let component: CvEditorComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    ({ fixture, component, http } = await setup('gen-1'));
  });

  afterEach(() => http.verify());

  it('loads the tailored CV named in ?generated=', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);
    http.expectOne('/api/cv/generated/gen-1').flush(tailoredCv());

    expect(component.cvForm.value.summary).toBe('Tailored summary');
    expect(component.cvForm.value.skillsText).toBe('python');
    expect(component.mode).toBe('edit');
    expect(component.message).toBe(
      component.i18n.t('cv.editingTailored', { job: 'Backend Engineer' })
    );
  });

  it('falls back to the current master CV when the tailored one is gone', () => {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);
    http
      .expectOne('/api/cv/generated/gen-1')
      .flush({ detail: 'not found' }, { status: 404, statusText: 'Not Found' });
    // The second /api/cv load brings the master document back into the editor.
    http.expectOne('/api/cv').flush([MASTER_CV]);

    expect(component.cvForm.value.summary).toBe(STRUCTURED.summary);
    expect(component.error).toBe(component.i18n.t('errors.failedLoadCV'));
  });
});

/** Build a change event-ish input element carrying a single file. */
function fileInput(name: string): HTMLInputElement {
  const input = document.createElement('input');
  Object.defineProperty(input, 'files', { value: [new File(['x'], name)] });
  return input;
}
