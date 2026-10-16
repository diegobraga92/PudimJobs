import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { JobCleanupResult, JobSummary } from '../../services/jobs.service';
import { Source } from '../../services/sources.service';
import { I18nService } from '../../services/i18n.service';
import { ToastService } from '../../shared/toast/toast.service';
import { JobsComponent } from './jobs.component';

const JOB: JobSummary = {
  id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
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
