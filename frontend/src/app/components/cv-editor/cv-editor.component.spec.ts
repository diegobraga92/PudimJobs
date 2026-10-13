import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { AtsReport, CVStructure, GeneratedCV, MasterCV } from '../../services/cv.service';
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

const REPORT: AtsReport = {
  score: 82,
  method: 'heuristic',
  factors: [
    { key: 'skills', label: 'Skill coverage', score: 0.8, weight: 0.4, detail: '4/5 skills.' },
  ],
  matched_skills: ['python', 'fastapi'],
  missing_skills: ['terraform'],
  recommendations: ['add or emphasise these required skills: terraform.'],
  warnings: [],
  llm_summary: null,
};

function generatedCv(): GeneratedCV {
  return {
    id: 'gen-1',
    master_cv_id: 'cv-1',
    job_id: 'job-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    created_at: '2026-02-01T00:00:00Z',
    structured_json: STRUCTURED,
    ats_score: 61,
    ats_report: REPORT,
  };
}

describe('CvEditorComponent', () => {
  let fixture: ComponentFixture<CvEditorComponent>;
  let component: CvEditorComponent;
  let http: HttpTestingController;

  function flushInitialRequests(generated: GeneratedCV[] = []): void {
    http.expectOne('/api/auth/me').flush({ id: 'u1', email: 'ada@example.com', role: 'user' });
    http.expectOne('/api/cv').flush([MASTER_CV]);
    http.expectOne('/api/cv/generated').flush(generated);
    http
      .expectOne('/api/jobs')
      .flush([
        {
          id: 'job-1',
          title: 'Backend Engineer',
          company: 'Acme',
          url: null,
          posted_date: null,
          tags: [],
          hidden: false,
          created_at: '2026-02-01T00:00:00Z',
        },
      ]);
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CvEditorComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(CvEditorComponent);
    component = fixture.componentInstance;
    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('pre-fills the editor from the current master CV (contact + certifications)', () => {
    flushInitialRequests();

    expect(component.cvForm.value.fullName).toBe('Ada Lovelace');
    expect(component.cvForm.value.contactEmail).toBe('ada@example.com');
    expect(component.cvForm.value.location).toBe('Lisbon, PT');
    expect(component.cvForm.value.linksText).toBe('https://github.com/ada');
    expect(component.cvForm.value.certificationsText).toBe('AWS Solutions Architect');
    expect(component.cvForm.value.languagesText).toBe('English');
    expect(component.displayName).toBe('Ada Lovelace');
    expect(component.jobs.length).toBe(1);
  });

  it('parses ODT uploads and rejects other extensions', () => {
    flushInitialRequests();

    const odt = fileInput('cv.odt');
    component.onFileSelected({ target: odt } as unknown as Event);
    http.expectOne('/api/cv/parse').flush({ ...STRUCTURED, summary: 'From ODT' });
    expect(component.cvForm.value.summary).toBe('From ODT');

    component.onFileSelected({ target: fileInput('cv.txt') } as unknown as Event);
    http.expectNone('/api/cv/parse');
    expect(component.error).toBe(component.i18n.t('errors.unsupportedCvFile'));
  });

  it('scores the editor content and renders the report', () => {
    flushInitialRequests();

    component.atsJobTitle = 'Backend Engineer';
    component.atsJobDescription = 'Python, FastAPI, Terraform.';
    component.scoreAts();

    const request = http.expectOne('/api/cv/ats-score');
    expect(request.request.body.job_title).toBe('Backend Engineer');
    expect(request.request.body.generated_cv_id).toBeNull();
    expect(request.request.body.cv.full_name).toBe('Ada Lovelace');
    expect(request.request.body.cv.skills).toEqual(['python', 'fastapi']);

    request.flush(REPORT);
    fixture.detectChanges();

    expect(component.atsReport?.score).toBe(82);
    const element = fixture.nativeElement as HTMLElement;
    const text = element.textContent ?? '';
    expect(text).toContain('82');
    expect(text).toContain('terraform');
    // score 82 → success badge, and the static `badge` class survives.
    expect(element.querySelector('.badge.badge-success')).toBeTruthy();
  });

  it('exports the current CV with the selected template', () => {
    flushInitialRequests();

    component.exportPdf('ats');

    const request = http.expectOne(
      (candidate) => candidate.url === '/api/cv/pdf' && candidate.params.get('template') === 'ats'
    );
    expect(request.request.responseType).toBe('blob');
    request.flush(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));

    expect(component.exporting).toBeFalse();
  });

  it('caches a tailored CV score via generated_cv_id', () => {
    flushInitialRequests([generatedCv()]);

    component.scoreGenerated(generatedCv());

    const request = http.expectOne('/api/cv/ats-score');
    expect(request.request.body.generated_cv_id).toBe('gen-1');
    expect(request.request.body.job_id).toBe('job-1');
    request.flush({ ...REPORT, score: 91 });

    // The cached report triggers a refresh of the tailored-CV list.
    http.expectOne('/api/cv/generated').flush([generatedCv()]);

    expect(component.atsReport?.score).toBe(91);
    expect(component.atsGeneratedId).toBe('gen-1');
  });
});

/** Build a change event-ish input element carrying a single file. */
function fileInput(name: string): HTMLInputElement {
  const input = document.createElement('input');
  Object.defineProperty(input, 'files', { value: [new File(['x'], name)] });
  return input;
}
