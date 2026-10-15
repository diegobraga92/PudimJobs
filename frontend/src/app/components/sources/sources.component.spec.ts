import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { I18nService } from '../../services/i18n.service';
import { ManualMetadata, Source } from '../../services/sources.service';
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
      providers: [provideHttpClient(), provideHttpClientTesting()],
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
});
