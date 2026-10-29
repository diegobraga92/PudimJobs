import { TestBed, ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { I18nService } from '../../services/i18n.service';
import { DiscoveryProvider, ManualMetadata, Source, SourceDiagnostics, SourceRunSummary } from '../../services/sources.service';
import { SourcesComponent } from './sources.component';

/** Exactly what `GET /api/sources/manual-metadata` publishes. */
const MANUAL_METADATA: ManualMetadata = {
  type: 'manual',
  cadence_days: { default: 7, min: 1, max: 365 },
  required_config: [],
  required_any: [],
  optional_config: ['cadence_days'],
  example_config: { cadence_days: 7 },
};

const SEARCH_PROVIDER: DiscoveryProvider = {
  name: 'brave',
  family: 'search_api',
  requires_key: true,
  required_config: ['query'],
  required_any: [],
  optional_config: ['max_pages'],
  example_config: { query: 'rust remote latam' },
};

const MANUAL_SOURCE: Source = {
  id: 'src-1',
  name: 'Login-walled board',
  url: 'https://protected.example/jobs',
  type: 'manual',
  config: {
    cadence_days: 5,
    next_check_at: '2030-01-01T00:00:00+00:00',
    reminded_at: '2026-01-01T00:00:00+00:00',
  },
  // The human note has its own column; it never travels inside `config`.
  notes: 'check the Slack #hiring channel',
  health: 'healthy',
  last_scraped: '2026-01-01T00:00:00+00:00',
  created_at: '2026-01-01T00:00:00+00:00',
  rate_limit_seconds: 30,
  respect_robots_txt: true,
  next_check_at: '2030-01-01T00:00:00+00:00',
  due: false,
};

describe('SourcesComponent — manual watchlist', () => {
  let fixture: ComponentFixture<SourcesComponent>;
  let component: SourcesComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SourcesComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(SourcesComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(I18nService).setLanguage('en');
    // ngOnInit loads the four contracts/lists; the form reads the manual one.
    fixture.detectChanges();
    http.expectOne('/api/sources').flush([]);
    http.expectOne('/api/sources/providers').flush([]);
    http.expectOne('/api/sources/adapters').flush([]);
    http.expectOne('/api/sources/manual-metadata').flush(MANUAL_METADATA);
  });

  afterEach(() => http.verify());

  it('keeps engine-managed config keys and sends the note separately', () => {
    component.openEdit(MANUAL_SOURCE);

    component.save();

    // PUT replaces config wholesale, so the form must merge: dropping
    // next_check_at/reminded_at would re-remind an already-checked source.
    const request = http.expectOne('/api/sources/src-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body.config).toEqual({
      cadence_days: 5,
      next_check_at: '2030-01-01T00:00:00+00:00',
      reminded_at: '2026-01-01T00:00:00+00:00',
    });
    // A human-only field, so it lives at the top level (sources.notes).
    expect(request.request.body.notes).toBe('check the Slack #hiring channel');
    request.flush(MANUAL_SOURCE);
    http.expectOne('/api/sources').flush([]); // save() refreshes the list
  });

  it('sends a null note when the field is cleared', () => {
    component.openEdit(MANUAL_SOURCE);
    component.cadenceDays = 21;
    component.notes = '   ';

    component.save();

    const request = http.expectOne('/api/sources/src-1');
    expect(request.request.body.config).toEqual({
      cadence_days: 21,
      next_check_at: '2030-01-01T00:00:00+00:00',
      reminded_at: '2026-01-01T00:00:00+00:00',
    });
    expect(request.request.body.notes).toBeNull();
    request.flush(MANUAL_SOURCE);
    http.expectOne('/api/sources').flush([]);
  });

  it('round-trips a note on a source type that is not a watchlist', () => {
    const source: Source = {
      ...MANUAL_SOURCE,
      id: 'src-rss',
      type: 'rss',
      config: { adapter: null },
      notes: 'feed drops the salary field',
    };
    component.openEdit(source);
    expect(component.notes).toBe('feed drops the salary field');

    component.notes = '  feed sometimes repeats jobs  ';
    component.save();

    const request = http.expectOne('/api/sources/src-rss');
    expect(request.request.body.notes).toBe('feed sometimes repeats jobs');
    request.flush(source);
    http.expectOne('/api/sources').flush([]);
  });

  it('never renders the note in the sources table', () => {
    component.sources = [MANUAL_SOURCE];
    fixture.detectChanges();

    const table = fixture.nativeElement.querySelector('.sources-table');
    expect(table.textContent).toContain('Login-walled board');
    expect(table.textContent).not.toContain('check the Slack #hiring channel');
  });

  it('shows the notes field when editing any source type', async () => {
    component.openEdit({ ...MANUAL_SOURCE, id: 'src-rss', type: 'rss', notes: 'keep this' });
    fixture.detectChanges();
    // `ngModel` writes its initial value after the first change-detection pass.
    await fixture.whenStable();
    fixture.detectChanges();

    const field = fixture.nativeElement.querySelector('#source-notes');
    expect(field).not.toBeNull();
    expect(field.value).toBe('keep this');
  });

  it('summarizes the schedule in a single-line meta under the last scrape', () => {
    // Manual: next check + how far away it is.
    expect(component.scrapedMeta(MANUAL_SOURCE)).toContain('Next check:');
    expect(component.scrapedMeta(MANUAL_SOURCE)).toContain('Due in');

    const rss: Source = {
      ...MANUAL_SOURCE,
      type: 'rss',
      scrape_interval_minutes: 1440,
      next_scrape_at: '2026-03-01T00:00:00+00:00',
      scrape_due: false,
    };
    expect(component.scrapedMeta(rss)).toContain('Next run:');
    expect(component.scrapedMeta(rss)).not.toContain('\n');
    expect(component.scrapedMeta({ ...rss, scrape_due: true })).toContain('due now');

    // Nothing scheduled yet: no meta line at all (the date still renders).
    expect(component.scrapedMeta({ ...MANUAL_SOURCE, next_check_at: null })).toBe('');
  });

  it('seeds a new manual source with the cadence the API publishes', () => {
    component.openCreate();

    expect(component.cadenceDays).toBe(MANUAL_METADATA.cadence_days.default);
    expect(component.notes).toBe('');
  });

  // --- Per-source scrape cadence (protects paid search credits) -------------

  it('defaults paid search providers to a weekly cadence', () => {
    component.openCreate();
    component.sourceForm.get('type')?.setValue('discovery');
    component.providers = [SEARCH_PROVIDER];

    component.onDiscoveryProviderChange('brave');

    expect(component.discoveryProvider).toBe('brave');
    expect(component.sourceForm.get('scrape_interval_minutes')?.value).toBe(10080);
  });

  it('does not overwrite an explicit cadence when a search provider is chosen', () => {
    component.openCreate();
    component.sourceForm.get('scrape_interval_minutes')?.setValue(1440);
    component.providers = [SEARCH_PROVIDER];

    component.onDiscoveryProviderChange('brave');

    expect(component.sourceForm.get('scrape_interval_minutes')?.value).toBe(1440);
  });

  it('keeps an API-set custom interval selectable', () => {
    component.openEdit({
      ...MANUAL_SOURCE,
      id: 'src-7',
      type: 'rss',
      scrape_interval_minutes: 120,
    });

    expect(component.scheduleOptions.map((option) => option.value)).toContain(120);
  });

  it('sends the per-source cadence on create', () => {
    component.openCreate();
    component.sourceForm.patchValue({
      name: 'Weekly board',
      url: 'https://weekly.example',
      type: 'rss',
      scrape_interval_minutes: 10080,
    });

    component.save();

    const request = http.expectOne('/api/sources');
    expect(request.request.method).toBe('POST');
    expect(request.request.body.scrape_interval_minutes).toBe(10080);
    request.flush({ ...MANUAL_SOURCE, id: 'src-6', type: 'rss' });
    http.expectOne('/api/sources').flush([]);
  });

  it('prefills and saves the location gate for every fetchable type', () => {
    const source: Source = {
      ...MANUAL_SOURCE,
      id: 'src-loc',
      type: 'career_page',
      config: { locations: ['Brazil', 'Remote'] },
    };
    component.openEdit(source);

    expect(component.locations).toBe('Brazil, Remote');

    component.locations = 'Brazil, São Paulo';
    component.save();

    const request = http.expectOne('/api/sources/src-loc');
    expect(request.request.method).toBe('PUT');
    // career_page sources had no config editor before: the dedicated field is
    // what lets them carry the gate, merged over the stored config.
    expect(request.request.body.config).toEqual({
      locations: ['Brazil', 'São Paulo'],
    });
    request.flush({ ...source, config: request.request.body.config });
    http.expectOne('/api/sources').flush([]);
  });

  it('drops the location gate when the field is cleared', () => {
    component.openEdit({
      ...MANUAL_SOURCE,
      id: 'src-loc',
      type: 'rss',
      config: { locations: ['Brazil'], company_from_title: true },
    });

    component.locations = '   ';
    component.save();

    const request = http.expectOne('/api/sources/src-loc');
    expect(request.request.body.config).toEqual({ company_from_title: true });
    request.flush({ ...MANUAL_SOURCE, id: 'src-loc', type: 'rss' });
    http.expectOne('/api/sources').flush([]);
  });

  it('takes the cadence input bounds from the API', () => {
    expect(component.cadenceMin).toBe(MANUAL_METADATA.cadence_days.min);
    expect(component.cadenceMax).toBe(MANUAL_METADATA.cadence_days.max);
  });

  // --- Preview: keyed providers borrow the saved source credentials ---------

  const BRAVE_SOURCE: Source = {
    ...MANUAL_SOURCE,
    id: 'src-brave',
    name: 'Brave search',
    url: 'https://search.example',
    type: 'discovery',
    config: { provider: 'brave', query: 'rust remote', count: 20 },
  };

  const PREVIEW_RESULT = {
    fetched_url: 'https://api.search.brave.com/res/v1/web/search',
    status_code: 200,
    jobs_found: 0,
    sample_jobs: [],
    truncated: false,
    error: null,
  };

  it('borrows the stored credentials of the source being edited', () => {
    component.providers = [SEARCH_PROVIDER];
    component.openEdit(BRAVE_SOURCE);

    component.preview();

    const request = http.expectOne('/api/sources/preview');
    expect(request.request.body.source_id).toBe('src-brave');
    expect(request.request.body.config).toEqual({
      query: 'rust remote',
      count: 20,
      provider: 'brave',
    });
    request.flush(PREVIEW_RESULT);
    expect(component.previewResult?.status_code).toBe(200);
  });

  it('does not borrow credentials when previewing a new source', () => {
    component.openCreate();
    component.sourceForm.patchValue({
      url: 'https://search.example',
      type: 'discovery',
    });
    component.providers = [SEARCH_PROVIDER];
    component.discoveryProvider = 'brave';
    component.configJson = '{"query":"rust remote"}';

    component.preview();

    const request = http.expectOne('/api/sources/preview');
    expect(request.request.body.source_id).toBeUndefined();
    request.flush(PREVIEW_RESULT);
  });

  it('labels an upcoming due date in days', () => {
    const soon = new Date(Date.now() + 3 * 86_400_000 - 60_000).toISOString();

    expect(component.dueText({ ...MANUAL_SOURCE, next_check_at: soon })).toBe('Due in 3 days');
  });

  it('labels a source that is due within the day', () => {
    const later = new Date(Date.now() + 60 * 60 * 1000).toISOString();

    expect(component.dueText({ ...MANUAL_SOURCE, next_check_at: later })).toBe(
      'Due within a day'
    );
  });

  it('labels a due date that already passed', () => {
    const justNow = new Date(Date.now() - 60_000).toISOString();
    const longAgo = new Date(Date.now() - 2 * 86_400_000 - 60_000).toISOString();

    expect(component.dueText({ ...MANUAL_SOURCE, next_check_at: justNow })).toBe('Due today');
    expect(component.dueText({ ...MANUAL_SOURCE, next_check_at: longAgo })).toBe(
      'Overdue by 2 days'
    );
  });

  it('has no due label for non-manual or unscheduled sources', () => {
    expect(component.dueText({ ...MANUAL_SOURCE, next_check_at: null })).toBe('');
    expect(component.dueText({ ...MANUAL_SOURCE, type: 'rss' })).toBe('');
  });

  // --- Avoid flag: a soft snooze that keeps the source listed (ADR 019) ---

  const ACTIVE_SOURCE: Source = { ...MANUAL_SOURCE, id: 'src-2', name: 'Good board' };
  const AVOIDED_SOURCE: Source = {
    ...MANUAL_SOURCE,
    id: 'src-3',
    name: 'Spammy board',
    avoided: true,
    avoided_at: '2026-01-02T00:00:00+00:00',
    avoid_reason: 'postings are never remote',
  };
  const UNHEALTHY_SOURCE: Source = {
    ...MANUAL_SOURCE,
    id: 'src-4',
    name: 'Broken board',
    type: 'rss',
    health: 'degraded',
  };
  const DUE_SOURCE: Source = {
    ...MANUAL_SOURCE,
    id: 'src-5',
    name: 'Due board',
    due: true,
  };

  it('lists avoided sources last and counts them', () => {
    component.sources = [AVOIDED_SOURCE, ACTIVE_SOURCE];

    expect(component.visibleSources.map((source) => source.id)).toEqual(['src-2', 'src-3']);
    expect(component.avoidedCount).toBe(1);
  });

  it('drops avoided sources from the table while "Hide avoided" is on', () => {
    component.sources = [AVOIDED_SOURCE, ACTIVE_SOURCE];

    component.toggleHideAvoided();
    expect(component.hideAvoided).toBe(true);
    expect(component.visibleSources.map((source) => source.id)).toEqual(['src-2']);

    component.toggleHideAvoided();
    expect(component.visibleSources.length).toBe(2);
  });

  // --- Quick filters: single-select chips above the table ---

  it('shows only manual sources when the Manual filter is active', () => {
    component.sources = [MANUAL_SOURCE, UNHEALTHY_SOURCE, ACTIVE_SOURCE];

    component.setSourceFilter('manual');

    expect(component.sourceFilter).toBe('manual');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      ACTIVE_SOURCE.id,
      MANUAL_SOURCE.id,
    ]);
  });

  it('shows only non-healthy sources when the Unhealthy filter is active', () => {
    component.sources = [MANUAL_SOURCE, UNHEALTHY_SOURCE];

    component.setSourceFilter('unhealthy');

    expect(component.visibleSources.map((source) => source.id)).toEqual([UNHEALTHY_SOURCE.id]);
    expect(component.unhealthyCount).toBe(1);
  });

  it('shows only due manual sources when the Due filter is active', () => {
    component.sources = [MANUAL_SOURCE, DUE_SOURCE, ACTIVE_SOURCE];

    component.setSourceFilter('due');

    expect(component.visibleSources.map((source) => source.id)).toEqual([DUE_SOURCE.id]);
    expect(component.dueCount).toBe(1);
  });

  it('shows only avoided sources when the Avoided filter is active', () => {
    component.sources = [ACTIVE_SOURCE, AVOIDED_SOURCE];

    component.setSourceFilter('avoided');

    expect(component.visibleSources.map((source) => source.id)).toEqual([AVOIDED_SOURCE.id]);
  });

  it('composes an active filter with "Hide avoided"', () => {
    component.sources = [ACTIVE_SOURCE, AVOIDED_SOURCE];

    component.setSourceFilter('manual');
    component.toggleHideAvoided();

    // Both are manual, but the avoided one is trimmed by the toggle.
    expect(component.visibleSources.map((source) => source.id)).toEqual([ACTIVE_SOURCE.id]);
  });

  it('restores every source when the All filter is selected again', () => {
    component.sources = [ACTIVE_SOURCE, UNHEALTHY_SOURCE];
    component.setSourceFilter('unhealthy');
    expect(component.visibleSources.length).toBe(1);

    component.setSourceFilter('');

    expect(component.sourceFilter).toBe('');
    expect(component.visibleSources.length).toBe(2);
  });

  it('counts manual and unhealthy sources for the chip counters', () => {
    component.sources = [MANUAL_SOURCE, ACTIVE_SOURCE, UNHEALTHY_SOURCE];

    expect(component.manualCount).toBe(2);
    expect(component.unhealthyCount).toBe(1);
  });

  it('avoids a source in one click, sending no reason so the stored one is kept', () => {
    component.sources = [ACTIVE_SOURCE];

    component.toggleAvoided(ACTIVE_SOURCE);

    const request = http.expectOne('/api/sources/src-2/avoid');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ avoided: true });
    request.flush({ ...ACTIVE_SOURCE, avoided: true, avoid_reason: 'kept' });

    expect(component.sources[0].avoided).toBe(true);
    expect(component.avoidingId).toBeNull();
    expect(component.error).toBeNull();
  });

  it('restores an avoided source from the list', () => {
    component.sources = [AVOIDED_SOURCE];

    component.toggleAvoided(AVOIDED_SOURCE);

    const request = http.expectOne('/api/sources/src-3/avoid');
    expect(request.request.body).toEqual({ avoided: false });
    request.flush({
      ...AVOIDED_SOURCE,
      avoided: false,
      avoid_reason: 'postings are never remote',
    });

    expect(component.sources[0].avoided).toBe(false);
  });

  it('seeds the avoid fields from the source being edited and clears them on create', () => {
    component.openEdit(AVOIDED_SOURCE);
    expect(component.avoidSource).toBe(true);
    expect(component.avoidReason).toBe('postings are never remote');

    component.openCreate();
    expect(component.avoidSource).toBe(false);
    expect(component.avoidReason).toBe('');
  });

  it('sends the avoid flag and reason when an edited source is saved', () => {
    component.openEdit(ACTIVE_SOURCE);
    component.avoidSource = true;
    component.avoidReason = '  recruiter spam  ';

    component.save();

    const request = http.expectOne('/api/sources/src-2');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body.avoided).toBe(true);
    expect(request.request.body.avoid_reason).toBe('recruiter spam');
    request.flush(ACTIVE_SOURCE);
    http.expectOne('/api/sources').flush([]); // save() refreshes the list
  });

  it('never sends the avoid flag when a new source is created', () => {
    component.openCreate();
    component.sourceForm.patchValue({ name: 'New board', url: 'https://new.example/jobs' });

    component.save();

    const request = http.expectOne('/api/sources');
    expect(request.request.method).toBe('POST');
    // `POST /sources` has no avoid fields — the flag only exists on later edits.
    expect(request.request.body).toEqual({
      name: 'New board',
      url: 'https://new.example/jobs',
      type: 'career_page',
      rate_limit_seconds: 30,
      scrape_interval_minutes: null,
      respect_robots_txt: true,
      notes: null,
      // No JSON in the textarea: the config is sent (PUT/POST replace it
      // wholesale) but carries no keys.
      config: {},
    });
    request.flush(ACTIVE_SOURCE);
    http.expectOne('/api/sources').flush([]);
  });

  // --- Jobs column + "View jobs": the deep link into the jobs list ---

  /** A scraped board: the only kind that collects jobs on its own. */
  const CAREER_SOURCE: Source = {
    ...MANUAL_SOURCE,
    id: 'src-6',
    name: 'Acme Careers',
    type: 'career_page',
    config: null,
    next_check_at: null,
    jobs_count: 7,
  };

  it('offers "View jobs" only for sources that can own jobs', () => {
    expect(component.canViewJobs(CAREER_SOURCE)).toBeTrue();
    // A watchlist is never fetched, so there is nothing to open…
    expect(component.canViewJobs(MANUAL_SOURCE)).toBeFalse();
    // …unless a job was attached to it by hand, which the count reveals.
    expect(component.canViewJobs({ ...MANUAL_SOURCE, jobs_count: 1 })).toBeTrue();
  });

  it('opens the jobs list narrowed to the source', () => {
    const navigate = spyOn(TestBed.inject(Router), 'navigate');

    component.viewJobs(CAREER_SOURCE);

    expect(navigate).toHaveBeenCalledWith(['/jobs'], { queryParams: { source_id: 'src-6' } });
  });

  it('renders the row actions as icon-only buttons with an accessible name', () => {
    component.sources = [CAREER_SOURCE, MANUAL_SOURCE];
    fixture.detectChanges();

    // Five labelled buttons per row used to be wider than the table itself, so
    // the last actions were clipped. The label now lives in `title` and the
    // accessible name has to say which source it acts on.
    const actions = fixture.debugElement.queryAll(
      By.css('tbody td.row-actions button, tbody td.row-actions a')
    );
    expect(actions.length).toBe(10);

    const labels = actions.map((action) => {
      const element = action.nativeElement as HTMLElement;
      // No visible text left in the button: only the icon renders.
      expect(element.textContent?.trim()).toBe('');
      expect(element.getAttribute('title')).withContext('tooltip').toBeTruthy();
      return element.getAttribute('aria-label');
    });

    expect(labels.filter((label) => !label)).toEqual([]);
    expect(labels).toContain('View the jobs from Acme Careers');
    expect(labels).toContain('Authentication settings for Acme Careers');
    expect(labels).toContain('Avoid Acme Careers');
    expect(labels).toContain('Edit source Acme Careers');
    expect(labels).toContain('Delete source Acme Careers');
    expect(labels).toContain('Open the board of Login-walled board');
    expect(labels).toContain('Mark Login-walled board as checked');
    // Delete stays the one danger-coloured action in the row.
    expect(
      fixture.debugElement.query(By.css('tbody td.row-actions button.btn-danger'))
    ).toBeTruthy();
  });

  it('shows only scraped boards when the Automated filter is active', () => {
    component.sources = [MANUAL_SOURCE, CAREER_SOURCE, UNHEALTHY_SOURCE];

    component.setSourceFilter('automated');

    expect(component.visibleSources.map((source) => source.id)).toEqual(['src-6', 'src-4']);
    expect(component.automatedCount).toBe(2);
  });

  // --- Column sorting: clicking a header toggles ascending/descending ---

  it('starts sorted alphabetically by name (A → Z)', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'charlie', name: 'Charlie board' },
      { ...ACTIVE_SOURCE, id: 'alpha', name: 'Alpha board' },
      { ...ACTIVE_SOURCE, id: 'bravo', name: 'Bravo board' },
    ];

    expect(component.sortKey).toBe('name');
    expect(component.sortDirection).toBe('asc');
    expect(component.ariaSort('name')).toBe('ascending');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'alpha',
      'bravo',
      'charlie',
    ]);
  });

  it('toggles the default name sort between descending and ascending', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'sort-b', name: 'Beta board' },
      { ...ACTIVE_SOURCE, id: 'sort-a', name: 'Alpha board' },
    ];

    // The list opens alphabetically, so the first click reverses it.
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-a', 'sort-b']);

    component.sortBy('name');
    expect(component.sortKey).toBe('name');
    expect(component.sortDirection).toBe('desc');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-b', 'sort-a']);

    component.sortBy('name');
    expect(component.sortDirection).toBe('asc');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-a', 'sort-b']);
  });

  it('starts a newly chosen column ascending', () => {
    component.sortBy('name');
    expect(component.sortDirection).toBe('desc');

    component.sortBy('jobs');

    expect(component.sortKey).toBe('jobs');
    expect(component.sortDirection).toBe('asc');
  });

  it('sorts by type using the label shown in the table', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'rss', type: 'rss' },
      { ...ACTIVE_SOURCE, id: 'aggregator', type: 'aggregator' },
      { ...ACTIVE_SOURCE, id: 'manual', type: 'manual' },
    ];

    component.sortBy('type');

    // Aggregator < Manual (watchlist) < RSS feed — the displayed labels.
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'aggregator',
      'manual',
      'rss',
    ]);
  });

  it('sorts jobs numerically and treats a missing count as zero', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'ten', jobs_count: 10 },
      { ...ACTIVE_SOURCE, id: 'none', jobs_count: undefined },
      { ...ACTIVE_SOURCE, id: 'two', jobs_count: 2 },
    ];

    component.sortBy('jobs');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['none', 'two', 'ten']);

    component.sortBy('jobs');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['ten', 'two', 'none']);
  });

  it('sorts health by severity rather than alphabetically', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'failing', health: 'failing' },
      { ...ACTIVE_SOURCE, id: 'healthy', health: 'healthy' },
      { ...ACTIVE_SOURCE, id: 'degraded', health: 'degraded' },
    ];

    component.sortBy('health');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'healthy',
      'degraded',
      'failing',
    ]);

    component.sortBy('health');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'failing',
      'degraded',
      'healthy',
    ]);
  });

  it('sorts by last scraped and keeps never-scraped sources last both ways', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'never', last_scraped: null },
      { ...ACTIVE_SOURCE, id: 'newer', last_scraped: '2026-03-01T00:00:00+00:00' },
      { ...ACTIVE_SOURCE, id: 'older', last_scraped: '2025-01-01T00:00:00+00:00' },
    ];

    component.sortBy('last_scraped');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'older',
      'newer',
      'never',
    ]);

    component.sortBy('last_scraped');
    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'newer',
      'older',
      'never',
    ]);
  });

  it('keeps avoided sources at the bottom of a descending sort', () => {
    component.sources = [
      { ...AVOIDED_SOURCE, id: 'avoided-z', name: 'Zzz avoided' },
      { ...ACTIVE_SOURCE, id: 'active-a', name: 'Aaa active' },
    ];

    component.sortBy('name'); // the default is ascending, so this reverses it

    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'active-a',
      'avoided-z',
    ]);
  });

  it('reports the sort direction through aria-sort', () => {
    expect(component.ariaSort('name')).toBe('ascending');

    component.sortBy('name');
    expect(component.ariaSort('name')).toBe('descending');
    expect(component.ariaSort('jobs')).toBeNull();

    component.sortBy('name');
    expect(component.ariaSort('name')).toBe('ascending');
  });

  it('sorts when a column header is clicked', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'sort-b', name: 'Beta board' },
      { ...ACTIVE_SOURCE, id: 'sort-a', name: 'Alpha board' },
    ];
    fixture.detectChanges();

    const header = fixture.debugElement.queryAll(By.css('thead th'))[0];
    const button = header.query(By.css('button.sort-header'));
    button.nativeElement.click();
    fixture.detectChanges();

    expect(component.sortKey).toBe('name');
    expect(header.nativeElement.getAttribute('aria-sort')).toBe('descending');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-b', 'sort-a']);
  });
});
describe('SourcesComponent — health panel', () => {
  const SKIPPED_RUN: SourceRunSummary = {
    status: 'skipped',
    error:
      'robots.txt unreachable at https://dev.pro/robots.txt (HTTP 503); will retry automatically',
    started_at: '2026-10-20T12:00:00+00:00',
    finished_at: '2026-10-20T12:00:01+00:00',
    new_jobs: 0,
  };

  const DEGRADED_SOURCE: Source = {
    id: 'src-devpro',
    name: 'Dev.pro',
    url: 'https://dev.pro/jobs',
    type: 'career_page',
    health: 'degraded',
    last_scraped: null,
    created_at: '2026-10-01T00:00:00+00:00',
    rate_limit_seconds: 20,
    respect_robots_txt: true,
    last_run: SKIPPED_RUN,
  };

  const DIAGNOSTICS: SourceDiagnostics = {
    source_id: 'src-devpro',
    name: 'Dev.pro',
    type: 'career_page',
    health: 'degraded',
    avoided: false,
    jobs_total: 42,
    unknown_company: 0,
    short_description: 0,
    missing_posted_date: 0,
    last_run_status: 'skipped',
    last_run_new_jobs: 0,
    last_run_error: SKIPPED_RUN.error,
    last_run_at: SKIPPED_RUN.started_at,
    last_run_finished_at: SKIPPED_RUN.finished_at,
    last_success_at: '2026-10-19T08:00:00+00:00',
    health_reason: SKIPPED_RUN.error,
    config_valid: true,
    config_error: null,
  };

  let fixture: ComponentFixture<SourcesComponent>;
  let component: SourcesComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SourcesComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(SourcesComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(I18nService).setLanguage('en');
    fixture.detectChanges();
    http.expectOne('/api/sources').flush([DEGRADED_SOURCE]);
    http.expectOne('/api/sources/providers').flush([]);
    http.expectOne('/api/sources/adapters').flush([]);
    http.expectOne('/api/sources/manual-metadata').flush(MANUAL_METADATA);
  });

  afterEach(() => http.verify());

  it('warns for degraded, names the reason and points at the unhealthy filter', () => {
    fixture.detectChanges();

    const badge = fixture.debugElement.query(By.css('.health-cell .badge'));
    expect(badge.nativeElement.textContent).toContain('Degraded');
    expect(badge.nativeElement.classList).toContain('badge-warning');
    expect(badge.nativeElement.classList).not.toContain('badge-danger');

    const reason = fixture.debugElement.query(By.css('.health-reason'));
    expect(reason.nativeElement.textContent).toContain('robots.txt unreachable');

    expect(fixture.nativeElement.textContent).toContain('1 source(s) need attention');
  });

  it('keeps the danger style for failing sources', () => {
    component.sources = [
      { ...DEGRADED_SOURCE, health: 'failing', last_run: { ...SKIPPED_RUN, status: 'failed' } },
    ];
    fixture.detectChanges();

    const badge = fixture.debugElement.query(By.css('.health-cell .badge'));
    expect(badge.nativeElement.textContent).toContain('Failing');
    expect(badge.nativeElement.classList).toContain('badge-danger');
  });

  it('loads diagnostics and the run history when the badge is opened', () => {
    component.openHealth(DEGRADED_SOURCE);
    expect(component.healthLoading).toBe(true);

    http.expectOne('/api/sources/src-devpro/diagnostics').flush(DIAGNOSTICS);
    http.expectOne('/api/sources/src-devpro/runs?limit=10').flush([SKIPPED_RUN]);
    fixture.detectChanges();

    expect(component.healthLoading).toBe(false);
    expect(component.healthReasonText).toContain('unreachable');
    expect(component.healthRuns.map((run) => run.status)).toEqual(['skipped']);
    expect(fixture.nativeElement.textContent).toContain('Last successful run');
  });

  it('re-checks a source now through the owner-scoped endpoint', () => {
    component.openHealth(DEGRADED_SOURCE);
    http.expectOne('/api/sources/src-devpro/diagnostics').flush(DIAGNOSTICS);
    http.expectOne('/api/sources/src-devpro/runs?limit=10').flush([SKIPPED_RUN]);

    component.scrapeNow();
    expect(component.scrapingId).toBe('src-devpro');

    const request = http.expectOne('/api/sources/src-devpro/scrape');
    expect(request.request.method).toBe('POST');
    request.flush({ enqueued: true, source_id: 'src-devpro' });

    expect(component.scrapingId).toBeNull();
  });

  it('does not offer a re-check for manual or avoided sources', () => {
    expect(component.canScrapeNow(MANUAL_SOURCE)).toBe(false);
    expect(component.canScrapeNow({ ...DEGRADED_SOURCE, avoided: true })).toBe(false);
    expect(component.canScrapeNow(DEGRADED_SOURCE)).toBe(true);
  });
});

