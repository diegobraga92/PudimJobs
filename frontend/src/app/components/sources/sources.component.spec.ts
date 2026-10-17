import { TestBed, ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { I18nService } from '../../services/i18n.service';
import { DiscoveryProvider, ManualMetadata, Source } from '../../services/sources.service';
import { SourcesComponent } from './sources.component';

/** Exactly what `GET /api/sources/manual-metadata` publishes. */
const MANUAL_METADATA: ManualMetadata = {
  type: 'manual',
  cadence_days: { default: 7, min: 1, max: 365 },
  required_config: [],
  required_any: [],
  optional_config: ['cadence_days', 'notes'],
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
    notes: 'check the Slack #hiring channel',
    next_check_at: '2030-01-01T00:00:00+00:00',
    reminded_at: '2026-01-01T00:00:00+00:00',
  },
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

  it('keeps engine-managed config keys when a manual source is edited', () => {
    component.openEdit(MANUAL_SOURCE);

    component.save();

    // PUT replaces config wholesale, so the form must merge: dropping
    // next_check_at/reminded_at would re-remind an already-checked source.
    const request = http.expectOne('/api/sources/src-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body.config).toEqual({
      cadence_days: 5,
      notes: 'check the Slack #hiring channel',
      next_check_at: '2030-01-01T00:00:00+00:00',
      reminded_at: '2026-01-01T00:00:00+00:00',
    });
    request.flush(MANUAL_SOURCE);
    http.expectOne('/api/sources').flush([]); // save() refreshes the list
  });

  it('drops the notes key when the field is cleared', () => {
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
    request.flush(MANUAL_SOURCE);
    http.expectOne('/api/sources').flush([]);
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

  it('takes the cadence input bounds from the API', () => {
    expect(component.cadenceMin).toBe(MANUAL_METADATA.cadence_days.min);
    expect(component.cadenceMax).toBe(MANUAL_METADATA.cadence_days.max);
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
      MANUAL_SOURCE.id,
      ACTIVE_SOURCE.id,
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
      respect_robots_txt: true,
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

  it('shows only scraped boards when the Automated filter is active', () => {
    component.sources = [MANUAL_SOURCE, CAREER_SOURCE, UNHEALTHY_SOURCE];

    component.setSourceFilter('automated');

    expect(component.visibleSources.map((source) => source.id)).toEqual(['src-6', 'src-4']);
    expect(component.automatedCount).toBe(2);
  });

  // --- Column sorting: clicking a header toggles ascending/descending ---

  it('sorts ascending on the first header click and descending on the next', () => {
    component.sources = [
      { ...ACTIVE_SOURCE, id: 'sort-b', name: 'Beta board' },
      { ...ACTIVE_SOURCE, id: 'sort-a', name: 'Alpha board' },
    ];

    component.sortBy('name');
    expect(component.sortKey).toBe('name');
    expect(component.sortDirection).toBe('asc');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-a', 'sort-b']);

    component.sortBy('name');
    expect(component.sortDirection).toBe('desc');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-b', 'sort-a']);
  });

  it('starts a newly chosen column ascending', () => {
    component.sortBy('name');
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

    component.sortBy('name');
    component.sortBy('name'); // descending would otherwise put Zzz first

    expect(component.visibleSources.map((source) => source.id)).toEqual([
      'active-a',
      'avoided-z',
    ]);
  });

  it('reports the sort direction through aria-sort', () => {
    expect(component.ariaSort('name')).toBeNull();

    component.sortBy('name');
    expect(component.ariaSort('name')).toBe('ascending');
    expect(component.ariaSort('jobs')).toBeNull();

    component.sortBy('name');
    expect(component.ariaSort('name')).toBe('descending');
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
    expect(header.nativeElement.getAttribute('aria-sort')).toBe('ascending');
    expect(component.visibleSources.map((source) => source.id)).toEqual(['sort-a', 'sort-b']);
  });
});
