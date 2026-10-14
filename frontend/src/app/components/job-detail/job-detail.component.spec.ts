import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { Application } from '../../services/applications.service';
import { I18nService } from '../../services/i18n.service';
import { JobDetail } from '../../services/jobs.service';
import { JobDetailComponent } from './job-detail.component';

const JOB: JobDetail = {
  id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
  url: 'https://acme.example/jobs/1',
  posted_date: '2026-02-01',
  tags: ['python'],
  hidden: false,
  created_at: '2026-02-01T00:00:00Z',
  description: '<p>Python, FastAPI, PostgreSQL.</p>',
  source_id: null,
};

const APPLICATION: Application = {
  id: 'app-1',
  job_id: 'job-1',
  status: 'applied',
  applied_date: '2026-02-02',
  notes: null,
  lessons_learned: null,
  generated_cv_id: null,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-02T00:00:00Z',
  job_title: 'Backend Engineer',
  job_company: 'Acme',
  job_url: 'https://acme.example/jobs/1',
};

/** The job page only triages: it links to the application workspace, never enqueues tailoring (ADR 015). */
describe('JobDetailComponent', () => {
  let fixture: ComponentFixture<JobDetailComponent>;
  let component: JobDetailComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [JobDetailComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: 'job-1' }) } },
        },
      ],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobDetailComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  /** Flushes the job, its parsed requirements and the pipeline lookup. */
  function loadJob(tracked: Application[] = []): void {
    http.expectOne('/api/jobs/job-1').flush(JOB);
    http.expectOne('/api/jobs/job-1/parsed').flush(null);
    http.expectOne('/api/applications').flush(tracked);
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function workspaceLink(): HTMLAnchorElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector('a.btn-primary');
  }

  it('tracks the job, then links to its application workspace', () => {
    loadJob();

    expect(text()).toContain('Add to applications');
    expect(workspaceLink()).toBeNull();

    const addButton = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button')
    ).find((button) => button.textContent?.includes('Add to applications'));
    addButton?.click();

    const request = http.expectOne('/api/applications');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ job_id: 'job-1', status: 'saved' });
    request.flush(APPLICATION);
    fixture.detectChanges();

    expect(component.application?.id).toBe('app-1');
    expect(workspaceLink()?.getAttribute('href')).toContain('/applications/app-1');
    expect(text()).toContain('Open workspace');
    // The job page never enqueues tailoring on its own.
    http.expectNone('/api/jobs/job-1/tailor');
  });

  it('links straight to the workspace when the job is already tracked', () => {
    loadJob([APPLICATION]);

    expect(component.application?.status).toBe('applied');
    expect(workspaceLink()?.getAttribute('href')).toContain('/applications/app-1');
    expect(text()).toContain('Applied');
    expect(text()).not.toContain('Add to applications');
    http.expectNone('/api/jobs/job-1/tailor');
  });

  it('reports a failed job load', () => {
    http.expectOne('/api/jobs/job-1').flush(
      { detail: 'Job not found' },
      { status: 404, statusText: 'Not Found' }
    );
    fixture.detectChanges();

    expect(component.job).toBeNull();
    expect(component.error).toBe(component.i18n.t('errors.failedLoadJob'));
    expect(text()).not.toContain('Open workspace');
  });
});
