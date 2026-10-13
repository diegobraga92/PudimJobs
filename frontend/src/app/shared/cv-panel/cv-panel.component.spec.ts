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
    source_master_cv_id: 'cv-master-1',
    variant: 'rule',
    job_id: 'job-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
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
    build('gen-1');
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    expect(component.selectedId).toBe('gen-1');
    expect(component.previewName).toBe('Ada Lovelace');
    expect(component.isLinked(component.tailored[0])).toBeTrue();
  });

  it('labels each variant and leaves the other one unlinked', () => {
    build('gen-1');
    const rule = tailored();
    const llm = tailored({
      id: 'gen-2',
      variant: 'llm',
      ats_score: 91,
      ats_report: { ...REPORT, llm_self_score: 95 },
    });
    http.expectOne((c) => c.url === '/api/cv/generated').flush([rule, llm]);

    expect(component.variantLabel(rule)).toBe('Deterministic');
    expect(component.variantLabel(llm)).toBe('AI rewrite');
    expect(component.isLinked(rule)).toBeTrue();
    expect(component.isLinked(llm)).toBeFalse();
  });

  it('explains why only the deterministic variant exists', () => {
    build('gen-1');
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);
    fixture.detectChanges();

    expect(component.llmVariantMissing).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Only the deterministic variant exists.');
  });

  it('hides the missing-variant hint once the AI rewrite exists', () => {
    build('gen-1');
    http
      .expectOne((c) => c.url === '/api/cv/generated')
      .flush([tailored(), tailored({ id: 'gen-2', variant: 'llm' })]);
    fixture.detectChanges();

    expect(component.llmVariantMissing).toBeFalse();
    expect(fixture.nativeElement.textContent).not.toContain(
      'Only the deterministic variant exists.'
    );
  });

  it('records the chosen variant as the CV that was sent', () => {
    build(null);
    http
      .expectOne((c) => c.url === '/api/cv/generated')
      .flush([tailored(), tailored({ id: 'gen-2', variant: 'llm' })]);

    component.useThisOne(component.tailored[1]);

    const request = http.expectOne('/api/applications/app-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ generated_cv_id: 'gen-2' });
    request.flush({ id: 'app-1', generated_cv_id: 'gen-2' });

    expect(component.linkedCvId).toBe('gen-2');
    expect(component.isLinked(component.tailored[1])).toBeTrue();
  });

  it('edits a tailored CV in place without touching the master CV', () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    component.startEdit();
    component.updateDraftSummary('Rewritten for Acme.');
    component.draftSkills = 'python, fastapi';
    component.saveEdit();

    const request = http.expectOne('/api/cv/generated/gen-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body.structured_json.summary).toBe('Rewritten for Acme.');
    expect(request.request.body.structured_json.skills).toEqual(['python', 'fastapi']);
    request.flush(
      tailored({
        structured_json: { ...STRUCTURED, summary: 'Rewritten for Acme.' },
        ats_score: null,
      })
    );

    expect(component.editing).toBeFalse();
    expect(component.saving).toBeFalse();
    expect(component.selectedStructure?.summary).toBe('Rewritten for Acme.');
  });

  it('drops an in-progress edit when switching version or cancelling', () => {
    build();
    http.expectOne((c) => c.url === '/api/cv/generated').flush([tailored()]);

    component.startEdit();
    component.updateDraftSummary('Half-written');
    component.cancelEdit();
    expect(component.editing).toBeFalse();
    expect(component.draft).toBeNull();

    component.startEdit();
    component.select(null);
    expect(component.editing).toBeFalse();
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
