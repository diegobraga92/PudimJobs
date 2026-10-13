import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { AtsReport, CVStructure, GeneratedCV } from '../../services/cv.service';
import { I18nService } from '../../services/i18n.service';
import { ConfirmService } from '../confirm/confirm.service';
import { CvPanelComponent } from './cv-panel.component';

const STRUCTURED: CVStructure = {
  full_name: 'Ada Lovelace',
  email: 'ada@example.com',
  phone: '+351 900 000 000',
  location: 'Lisbon, PT',
  links: [],
  summary: 'Tailored for Acme.',
  experience: [],
  education: [],
  skills: ['python'],
  projects: [],
  certifications: [],
  languages: [],
};

const REPORT: AtsReport = {
  score: 82,
  method: 'heuristic',
  factors: [
    { key: 'skills', label: 'Skill coverage', score: 0.8, weight: 0.4, detail: '4/5 skills.' },
  ],
  matched_skills: ['python'],
  missing_skills: ['terraform'],
  recommendations: ['add or emphasise these required skills: terraform.'],
  warnings: [],
  llm_summary: null,
};

function tailored(overrides: Partial<GeneratedCV> = {}): GeneratedCV {
  return {
    id: 'gen-1',
    master_cv_id: 'cv-master-1',
    job_id: 'job-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    created_at: '2026-02-01T00:00:00Z',
    structured_json: STRUCTURED,
    ats_score: null,
    ats_report: null,
    ...overrides,
  };
}

describe('CvPanelComponent', () => {
  let fixture: ComponentFixture<CvPanelComponent>;
  let component: CvPanelComponent;
  let http: HttpTestingController;

  function build(linkedCvId: string | null = null): void {
    fixture = TestBed.createComponent(CvPanelComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('jobId', 'job-1');
    fixture.componentRef.setInput('jobTitle', 'Backend Engineer');
    fixture.componentRef.setInput('applicationId', 'app-1');
    fixture.componentRef.setInput('linkedCvId', linkedCvId);
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CvPanelComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('scopes the tailored-CV lookup to this job', () => {
    build();
    const request = http.expectOne((c) => c.url === '/api/cv/generated');
    expect(request.request.params.get('job_id')).toBe('job-1');
    request.flush([]);

    expect(component.tailored).toEqual([]);
    expect(component.selectedId).toBeNull();
  });

  it('previews the newest tailored CV and flags the one sent with the application', () => {
    build('cv-master-1');
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    expect(component.selectedId).toBe('gen-1');
    expect(component.previewName).toBe('Ada Lovelace');
    expect(component.isLinked(component.tailored[0])).toBeTrue();
  });

  it('scores the selected tailored CV against the job and caches the report', () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    component.score();

    const request = http.expectOne('/api/cv/ats-score');
    expect(request.request.body.job_id).toBe('job-1');
    expect(request.request.body.generated_cv_id).toBe('gen-1');
    expect(request.request.body.cv.summary).toBe('Tailored for Acme.');
    request.flush(REPORT);

    // The cached report triggers a reload so the list badge refreshes.
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored({ ats_score: 82 })]);

    expect(component.report?.score).toBe(82);
    expect(component.tailored[0].ats_score).toBe(82);
  });

  it('enqueues tailoring linked to the application and shows the pending state', () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);

    component.tailor();

    const request = http.expectOne('/api/jobs/job-1/tailor');
    expect(request.request.body.application_id).toBe('app-1');
    expect(request.request.body['cv_id']).toBeUndefined();
    request.flush({ enqueued: true, job_id: 'job-1', application_id: 'app-1' });

    expect(component.pending).toBeTrue();
    expect(component.tailoring).toBeFalse();
  });

  it('resolves the pending state once the artifact shows up', () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);
    component.pending = true;

    component.load();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    expect(component.pending).toBeFalse();
    expect(component.selectedId).toBe('gen-1');
  });

  it('deletes a tailored CV and reloads the list', async () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    const pending = component.remove(component.tailored[0]);
    TestBed.inject(ConfirmService).close(true);
    await pending;

    http.expectOne('/api/cv/generated/gen-1').flush(null, { status: 204, statusText: 'No Content' });
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);

    expect(component.tailored).toEqual([]);
    expect(component.selectedId).toBeNull();
  });
});
