import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { JobCleanupResult, JobSummary } from '../../services/jobs.service';
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

const SOURCE = { id: 'src-1', name: 'Acme Careers' };

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

  /** The two requests the list fires on init. */
  function flushInit(): void {
    http.expectOne((c) => c.url === '/api/jobs').flush([JOB]);
    http.expectOne((c) => c.url === '/api/applications').flush([]);
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
