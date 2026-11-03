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
  location: 'Remote, Brazil',
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

  /** A button whose visible label contains `label` (the actions row mixes several). */
  function button(label: string): HTMLButtonElement | undefined {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button')
    ).find((item) => item.textContent?.includes(label));
  }

  /** The rendered description markup, exactly as the page shows it. */
  function descriptionMarkup(): string {
    const node = (fixture.nativeElement as HTMLElement).querySelector('.description');
    return node?.innerHTML?.trim() ?? '';
  }

  it('opens the edit dialog pre-filled with what the source stored', () => {
    loadJob();

    button('Edit job')?.click();
    fixture.detectChanges();

    expect(component.editOpen).toBeTrue();
    expect(component.editForm.value).toEqual({
      title: 'Backend Engineer',
      company: 'Acme',
      location: 'Remote, Brazil',
      url: 'https://acme.example/jobs/1',
      posted_date: '2026-02-01',
      tags: 'python',
      description: '<p>Python, FastAPI, PostgreSQL.</p>',
    });
  });

  it('saves the edited fields and re-queues parsing for a new description', () => {
    loadJob();
    component.openEdit();
    component.editForm.patchValue({
      description: 'Kubernetes and Go.\nOwn the platform.',
      tags: 'go, kubernetes',
    });

    component.saveEdit();

    const request = http.expectOne('/api/jobs/job-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      title: 'Backend Engineer',
      company: 'Acme',
      location: 'Remote, Brazil',
      url: 'https://acme.example/jobs/1',
      posted_date: '2026-02-01',
      tags: ['go', 'kubernetes'],
      description: 'Kubernetes and Go.\nOwn the platform.',
    });
    request.flush({
      ...JOB,
      description: 'Kubernetes and Go.\nOwn the platform.',
      tags: ['go', 'kubernetes'],
    });

    // New text means new requirements: the stale parse is dropped and re-queued.
    http
      .expectOne({ url: '/api/jobs/job-1/parse', method: 'POST' })
      .flush({ enqueued: true, job_id: 'job-1' });
    fixture.detectChanges();

    expect(component.editOpen).toBeFalse();
    expect(component.parsed).toBeNull();
    expect(component.message).toBe(component.i18n.t('jobDetail.saved'));
    // A hand-typed description keeps its line breaks instead of collapsing.
    expect(descriptionMarkup()).toContain('Kubernetes and Go.<br>Own the platform.');
  });

  it('does not re-queue parsing when only other fields change', () => {
    loadJob();
    component.openEdit();
    component.editForm.patchValue({ title: 'Staff Engineer' });

    component.saveEdit();

    http.expectOne('/api/jobs/job-1').flush({ ...JOB, title: 'Staff Engineer' });

    http.expectNone({ url: '/api/jobs/job-1/parse', method: 'POST' });
    expect(component.job?.title).toBe('Staff Engineer');
  });

  it('keeps the dialog open and explains a failed save', () => {
    loadJob();
    component.openEdit();
    component.editForm.patchValue({ description: 'Anything.' });

    component.saveEdit();

    http
      .expectOne('/api/jobs/job-1')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    // The page must not be replaced by the error: the typed text lives here.
    expect(component.editOpen).toBeTrue();
    expect(component.editError).toBe(component.i18n.t('errors.failedUpdateJob'));
    expect(component.editForm.value.description).toBe('Anything.');
    expect(text()).toContain(component.i18n.t('jobDetail.editHint'));
  });

  it('offers to add a description when the source stored none', () => {
    http.expectOne('/api/jobs/job-1').flush({ ...JOB, description: null });
    http.expectOne('/api/jobs/job-1/parsed').flush(null);
    http.expectOne('/api/applications').flush([]);
    fixture.detectChanges();

    expect(text()).toContain(component.i18n.t('jobDetail.missingDescription'));
    expect(descriptionMarkup()).toBe(component.i18n.t('jobDetail.noDescription'));

    button('Add description')?.click();
    fixture.detectChanges();

    expect(component.editOpen).toBeTrue();
    expect(component.editForm.value.description).toBe('');
  });
});
