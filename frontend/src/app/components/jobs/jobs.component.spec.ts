import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { JobCleanupResult, JobImportPreview, JobSummary } from '../../services/jobs.service';
import { Source } from '../../services/sources.service';
import { I18nService } from '../../services/i18n.service';
import { ToastService } from '../../shared/toast/toast.service';
import { JobsComponent } from './jobs.component';

const JOB: JobSummary = {
  id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
  location: 'Remote, Brazil',
  url: null,
  posted_date: null,
  tags: [],
  hidden: false,
  created_at: '2026-01-01T00:00:00Z',
};

const SOURCE: Source = {
  id: 'src-1',
  name: 'Acme Careers',
  url: 'https://acme.example/careers',
  type: 'career_page',
  health: 'healthy',
  last_scraped: '2026-01-01T00:00:00+00:00',
  created_at: '2026-01-01T00:00:00+00:00',
  jobs_count: 3,
  rate_limit_seconds: 30,
  respect_robots_txt: true,
};

/** A watchlist: never fetched, so it owns no jobs and is offered nowhere. */
const MANUAL_SOURCE: Source = {
  ...SOURCE,
  id: 'src-2',
  name: 'Login-walled board',
  type: 'manual',
  jobs_count: 0,
};

function preview(matched = 2, protectedCount = 0): JobCleanupResult {
  return { matched, deleted: 0, protected: protectedCount, dry_run: true };
}

/** What `POST /api/jobs/import-preview` returns for a readable posting. */
const DRAFT: JobImportPreview = {
  fetched_url: 'https://acme.example/jobs/1',
  status_code: 200,
  url: 'https://acme.example/jobs/1',
  title: 'Staff Engineer',
  company: 'Acme',
  location: 'Remote, Brazil',
  description: 'Own the API.',
  posted_date: '2026-02-01',
  tags: ['python', 'fastapi'],
  extraction: 'json_ld',
  llm_used: false,
  warnings: [],
  existing_job_id: null,
  error: null,
};

describe('JobsComponent (bulk cleanup, ADR 023)', () => {
  let fixture: ComponentFixture<JobsComponent>;
  let component: JobsComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [JobsComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    localStorage.removeItem('pudimjobs_jobs_last_visit');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  /** The three requests the list fires on init. */
  function flushInit(sources: Source[] = []): void {
    http.expectOne((c) => c.url === '/api/jobs').flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http.expectOne((c) => c.url === '/api/sources').flush(sources);
  }

  /** Open the dialog and settle its source lookup. */
  function openCleanup(): void {
    component.openCleanup();
    http.expectOne((c) => c.url === '/api/sources').flush([SOURCE]);
  }

  it('does not narrow the default feed by created_after', () => {
    flushInit();

    component.searchForm.patchValue({ added: '' });
    component.search();
    const list = http.expectOne((c) => c.url === '/api/jobs');

    expect(list.request.params.has('created_after')).toBeFalse();
    list.flush([]);
  });

  it('sends the location filter and can exclude unknown locations', () => {
    flushInit();

    component.searchForm.patchValue({ location: 'Brazil' });
    component.search();
    let list = http.expectOne((c) => c.url === '/api/jobs');

    expect(list.request.params.get('location')).toBe('Brazil');
    // Unknown-location jobs are included by default.
    expect(list.request.params.has('location_unknown')).toBeFalse();
    list.flush([]);

    component.toggleIncludeUnknownLocation();
    list = http.expectOne((c) => c.url === '/api/jobs');

    // `false` is a meaningful value here, so the service must not drop it.
    expect(list.request.params.get('location_unknown')).toBe('false');
    list.flush([]);
  });

  it('sends hide_applied by default and drops it when the box is unticked', () => {
    // On by default: the feed request issued on init is already narrowed.
    const initial = http.expectOne((c) => c.url === '/api/jobs');
    expect(initial.request.params.get('hide_applied')).toBe('true');
    initial.flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http.expectOne((c) => c.url === '/api/sources').flush([]);

    component.toggleHideApplied();
    let list = http.expectOne((c) => c.url === '/api/jobs');

    // Off: the param is omitted, not sent as `false`.
    expect(list.request.params.has('hide_applied')).toBeFalse();
    list.flush([]);

    component.toggleHideApplied();
    list = http.expectOne((c) => c.url === '/api/jobs');

    expect(list.request.params.get('hide_applied')).toBe('true');
    list.flush([]);
  });

  it('translates the Added window into an ISO created_after cutoff', () => {
    flushInit();

    component.searchForm.patchValue({ added: '24h' });
    const before = Date.now();
    component.search();
    const list = http.expectOne((c) => c.url === '/api/jobs');

    const cutoff = Date.parse(list.request.params.get('created_after') ?? '');
    expect(Number.isFinite(cutoff)).toBeTrue();
    expect(Math.abs(before - 24 * 60 * 60 * 1000 - cutoff)).toBeLessThan(5000);
    list.flush([]);
  });

  it('uses the visit captured on mount for since-last-visit', () => {
    flushInit();
    const previous = '2026-10-01T12:00:00.000Z';
    (component as unknown as { previousVisit: string | null }).previousVisit = previous;

    component.searchForm.patchValue({ added: 'last_visit' });
    component.search();
    const list = http.expectOne((c) => c.url === '/api/jobs');

    expect(list.request.params.get('created_after')).toBe(previous);
    list.flush([]);
  });

  it('records a last-visit timestamp after the first successful load', () => {
    const before = Date.now();
    flushInit();

    const stored = Date.parse(localStorage.getItem('pudimjobs_jobs_last_visit') ?? '');
    expect(Number.isFinite(stored)).toBeTrue();
    expect(stored).toBeGreaterThanOrEqual(before);
  });

  it('marks jobs added in the last 48 hours as new', () => {
    flushInit();

    expect(component.isNew({ ...JOB, created_at: new Date().toISOString() })).toBeTrue();
    expect(component.isNew(JOB)).toBeFalse();
  });

  it('previews with dry_run and deletes nothing', () => {
    flushInit();
    openCleanup();
    component.cleanupForm.patchValue({ older_than_days: 60, source_id: 'src-1' });

    component.previewCleanup();

    const request = http.expectOne((c) => c.url === '/api/jobs/cleanup');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      older_than_days: 60,
      source_id: 'src-1',
      include_with_applications: false,
      dry_run: true,
    });
    request.flush(preview(2, 1));

    expect(component.cleanupPreview?.matched).toBe(2);
    expect(component.cleanupPreview?.protected).toBe(1);
    // The dialog stays open so the user can decide on the real run.
    expect(component.showCleanup).toBeTrue();
  });

  it('runs the deletion with dry_run off and refreshes the list', () => {
    flushInit();
    openCleanup();

    component.previewCleanup();
    http.expectOne((c) => c.url === '/api/jobs/cleanup').flush(preview());
    component.runCleanup();

    const request = http.expectOne((c) => c.url === '/api/jobs/cleanup');
    expect(request.request.body?.dry_run).toBeFalse();
    request.flush({ matched: 2, deleted: 2, protected: 0, dry_run: false });

    // The list and the pipeline map are reloaded so the cards disappear.
    http.expectOne((c) => c.url === '/api/jobs').flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);

    expect(component.showCleanup).toBeFalse();
    expect(component.cleanupPreview).toBeNull();
  });

  it('sends the include_with_applications opt-in when the user ticks it', () => {
    flushInit();
    openCleanup();
    component.cleanupForm.patchValue({
      older_than_days: null,
      source_id: 'src-1',
      include_with_applications: true,
    });

    component.previewCleanup();

    const request = http.expectOne((c) => c.url === '/api/jobs/cleanup');
    expect(request.request.body).toEqual({
      older_than_days: null,
      source_id: 'src-1',
      include_with_applications: true,
      dry_run: true,
    });
    request.flush(preview(1));
  });

  it('leaves the confirm button disabled while every match is protected', () => {
    flushInit();
    openCleanup();

    expect(component.cleanupHasDeletions).toBeFalse();

    component.previewCleanup();
    http.expectOne((c) => c.url === '/api/jobs/cleanup').flush(preview(3, 3));
    expect(component.cleanupHasDeletions).toBeFalse();

    component.previewCleanup();
    http.expectOne((c) => c.url === '/api/jobs/cleanup').flush(preview(3, 1));
    expect(component.cleanupHasDeletions).toBeTrue();
  });

  it('refuses an empty criteria without calling the API', () => {
    flushInit();
    openCleanup();
    const toast = TestBed.inject(ToastService);
    const error = spyOn(toast, 'error');
    component.cleanupForm.patchValue({ older_than_days: null, source_id: '' });

    component.previewCleanup();

    http.expectNone((c) => c.url === '/api/jobs/cleanup');
    expect(error).toHaveBeenCalledWith(component.i18n.t('jobs.cleanup.needCriteria'));
  });

  it('surfaces a failed preview instead of leaving the dialog stuck', () => {
    flushInit();
    openCleanup();
    const toast = TestBed.inject(ToastService);
    const error = spyOn(toast, 'error');

    component.previewCleanup();
    http
      .expectOne((c) => c.url === '/api/jobs/cleanup')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(error).toHaveBeenCalledWith(component.i18n.t('errors.failedCleanupJobs'));
    expect(component.cleanupRunning).toBeFalse();
    expect(component.cleanupPreview).toBeNull();
  });
});

describe('JobsComponent — source filter', () => {
  let http: HttpTestingController;

  /**
   * Builds the list with `?source_id=<id>` already in the URL (or not). Mounted
   * per test because the param is read once, when the component initializes.
   */
  async function mount(sourceId: string | null): Promise<ComponentFixture<JobsComponent>> {
    await TestBed.configureTestingModule({
      imports: [JobsComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap(sourceId ? { source_id: sourceId } : {}),
            },
          },
        },
      ],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    localStorage.removeItem('pudimjobs_jobs_last_visit');
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(JobsComponent);
    fixture.detectChanges();
    return fixture;
  }

  /** Settle the three requests fired on init (jobs, pipeline, sources). */
  function flushInit(sources: Source[] = []): void {
    http.expectOne((c) => c.url === '/api/jobs').flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http.expectOne((c) => c.url === '/api/sources').flush(sources);
  }

  afterEach(() => http.verify());

  it('sends the picked board with the search', async () => {
    const fixture = await mount(null);
    flushInit();

    fixture.componentInstance.searchForm.patchValue({ source_id: 'src-1' });
    fixture.componentInstance.search();

    const list = http.expectOne((c) => c.url === '/api/jobs');
    expect(list.request.params.get('source_id')).toBe('src-1');
    list.flush([]);
  });

  it('offers only boards that can own jobs in the dropdown', async () => {
    const fixture = await mount(null);

    flushInit([SOURCE, MANUAL_SOURCE]);

    expect(fixture.componentInstance.sourceOptions.map((source) => source.id)).toEqual(['src-1']);
  });

  it('still offers a watchlist that owns a job added by hand', async () => {
    const fixture = await mount(null);

    flushInit([{ ...MANUAL_SOURCE, jobs_count: 1 }]);

    expect(fixture.componentInstance.sourceOptions.map((source) => source.id)).toEqual(['src-2']);
  });

  it('seeds the filter from ?source_id= before the first search', async () => {
    const fixture = await mount('src-1');

    // The very first list request already carries the board — no unfiltered flash.
    const list = http.expectOne((c) => c.url === '/api/jobs');
    expect(list.request.params.get('source_id')).toBe('src-1');
    list.flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http.expectOne((c) => c.url === '/api/sources').flush([SOURCE]);

    expect(fixture.componentInstance.searchForm.value.source_id).toBe('src-1');
    expect(fixture.componentInstance.activeSourceLabel).toBe('Source: Acme Careers');
  });

  it('names the active board and clears it in one click', async () => {
    const fixture = await mount(null);
    flushInit([SOURCE]);
    const component = fixture.componentInstance;
    expect(component.activeSourceLabel).toBe('');

    component.searchForm.patchValue({ source_id: 'src-1' });
    expect(component.activeSourceLabel).toBe('Source: Acme Careers');

    component.clearSourceFilter();

    const list = http.expectOne((c) => c.url === '/api/jobs');
    expect(list.request.params.has('source_id')).toBeFalse();
    list.flush([]);
    expect(component.activeSourceLabel).toBe('');
  });

  it('falls back to a generic label for a board it does not know', async () => {
    const fixture = await mount('src-deleted');

    flushInit([]);

    expect(fixture.componentInstance.activeSourceLabel).toBe('Narrowed to one source');
  });

  it('degrades silently when the sources request fails', async () => {
    const fixture = await mount(null);
    http.expectOne((c) => c.url === '/api/jobs').flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http
      .expectOne((c) => c.url === '/api/sources')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    const component = fixture.componentInstance;
    expect(component.sourceOptions).toEqual([]);
    expect(component.error).toBeNull();
  });
});

describe('JobsComponent — import from a URL (ADR 025)', () => {
  let fixture: ComponentFixture<JobsComponent>;
  let component: JobsComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [JobsComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    localStorage.removeItem('pudimjobs_jobs_last_visit');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function flushInit(): void {
    http.expectOne((c) => c.url === '/api/jobs').flush([]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    http.expectOne((c) => c.url === '/api/sources').flush([]);
  }

  /** Open the Add-job dialog and paste a URL, without importing yet. */
  function prepare(url = 'https://acme.example/jobs/1'): void {
    flushInit();
    component.openCreate();
    component.jobForm.patchValue({ import_url: `  ${url}  ` });
  }

  it('pre-fills the form from the draft and saves it through POST /api/jobs', () => {
    prepare();

    component.importFromUrl();

    const request = http.expectOne((c) => c.url === '/api/jobs/import-preview');
    expect(request.request.method).toBe('POST');
    // The pasted value is trimmed before it leaves the browser.
    expect(request.request.body).toEqual({ url: 'https://acme.example/jobs/1' });
    request.flush(DRAFT);

    expect(component.importing).toBeFalse();
    expect(component.importError).toBeNull();
    expect(component.jobForm.get('title')?.value).toBe('Staff Engineer');
    expect(component.jobForm.get('company')?.value).toBe('Acme');
    expect(component.jobForm.get('location')?.value).toBe('Remote, Brazil');
    expect(component.jobForm.get('url')?.value).toBe('https://acme.example/jobs/1');
    expect(component.jobForm.get('posted_date')?.value).toBe('2026-02-01');
    expect(component.jobForm.get('tags')?.value).toBe('python, fastapi');
    expect(component.jobForm.get('description')?.value).toBe('Own the API.');
    expect(component.importedHost).toBe('acme.example');
    // Nothing is saved until the user presses Save.
    http.expectNone((c) => c.url === '/api/jobs' && c.method === 'POST');

    component.save();

    const created = http.expectOne((c) => c.url === '/api/jobs' && c.method === 'POST');
    expect(created.request.body).toEqual({
      title: 'Staff Engineer',
      company: 'Acme',
      location: 'Remote, Brazil',
      url: 'https://acme.example/jobs/1',
      posted_date: '2026-02-01',
      description: 'Own the API.',
      tags: ['python', 'fastapi'],
    });
    created.flush({ ...JOB, id: 'job-9' });

    // An imported description is parsed right away (skills + score).
    http
      .expectOne({ url: '/api/jobs/job-9/parse', method: 'POST' })
      .flush({ enqueued: true, job_id: 'job-9' });
    http.expectOne((c) => c.url === '/api/jobs').flush([]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    expect(component.showForm).toBeFalse();
    expect(component.importedFromUrl).toBeFalse();
  });

  it('keeps what the user typed when the draft has an empty field', () => {
    prepare();
    component.jobForm.patchValue({ title: 'My own title' });
    component.importFromUrl();
    http
      .expectOne((c) => c.url === '/api/jobs/import-preview')
      .flush({ ...DRAFT, title: '', location: null });

    expect(component.jobForm.get('title')?.value).toBe('My own title');
    expect(component.jobForm.get('company')?.value).toBe('Acme');
  });


  it('explains an unreadable page and leaves the form usable', () => {
    prepare();
    component.importFromUrl();
    http.expectOne((c) => c.url === '/api/jobs/import-preview').flush({
      ...DRAFT,
      title: '',
      company: '',
      description: null,
      tags: [],
      extraction: 'none',
      warnings: ['the page has no readable job description'],
      error: 'timed out after 15s — the site may be slow or JS-rendered',
    });

    expect(component.importError).toContain('timed out');
    expect(component.importWarnings).toEqual(['the page has no readable job description']);
    // A failed import is not a successful one: nothing is enqueued on save.
    expect(component.importedFromUrl).toBeFalse();
    // An empty field is never patched, so the user's own value (or a blank
    // control, `null` after `reset()`) is what the form keeps.
    expect(component.jobForm.get('company')?.value).toBeFalsy();
    expect(component.jobForm.get('title')?.value).toBeFalsy();
  });

  it('warns about an already saved URL without blocking the draft', () => {
    prepare();
    component.importFromUrl();
    http
      .expectOne((c) => c.url === '/api/jobs/import-preview')
      .flush({ ...DRAFT, existing_job_id: 'job-1' });

    expect(component.existingJobId).toBe('job-1');
    expect(component.importedFromUrl).toBeTrue();

    component.openExistingJob();
    expect(component.showForm).toBeFalse();
  });

  it('flags that the AI reader filled fields', () => {
    prepare();
    component.importFromUrl();
    http
      .expectOne((c) => c.url === '/api/jobs/import-preview')
      .flush({ ...DRAFT, llm_used: true });

    expect(component.importUsedLlm).toBeTrue();
  });

  it('refuses an empty URL without calling the API', () => {
    flushInit();
    component.openCreate();
    const toast = TestBed.inject(ToastService);
    const error = spyOn(toast, 'error');

    component.importFromUrl();

    http.expectNone((c) => c.url === '/api/jobs/import-preview');
    expect(error).toHaveBeenCalledWith(component.i18n.t('errors.importUrlRequired'));
    expect(component.importing).toBeFalse();
  });

  it('surfaces a transport failure instead of leaving the dialog stuck', () => {
    prepare();
    component.importFromUrl();
    http
      .expectOne((c) => c.url === '/api/jobs/import-preview')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(component.importing).toBeFalse();
    expect(component.importError).toBe(component.i18n.t('errors.failedImportJob'));
  });

  it('sends null for a cleared posted date (422 guard)', () => {
    flushInit();
    component.openCreate();
    component.jobForm.patchValue({ title: 'Backend Engineer', company: 'Acme', posted_date: '' });

    component.save();

    const created = http.expectOne((c) => c.url === '/api/jobs' && c.method === 'POST');
    expect(created.request.body.posted_date).toBeNull();
    created.flush({ ...JOB, id: 'job-7' });
    http.expectOne((c) => c.url === '/api/jobs').flush([]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
    // Not imported: no parse request.
    http.expectNone((c) => c.url === '/api/jobs/job-7/parse');
  });
});

