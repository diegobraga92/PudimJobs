import { TestBed, ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { ApplicationDetail } from '../../services/applications.service';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { I18nService } from '../../services/i18n.service';
import { ApplicationDetailComponent } from './application-detail.component';

const APPLICATION: ApplicationDetail = {
  id: 'app-1',
  job_id: 'job-1',
  status: 'applied',
  applied_date: '2026-02-02',
  notes: 'Referred by Jo.',
  lessons_learned: null,
  cv_version: null,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-02T00:00:00Z',
  job_title: 'Backend Engineer',
  job_company: 'Acme',
  job_url: 'https://acme.example/jobs/1',
  job_description: 'Python, FastAPI, PostgreSQL.',
};

describe('ApplicationDetailComponent', () => {
  let fixture: ComponentFixture<ApplicationDetailComponent>;
  let component: ApplicationDetailComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ApplicationDetailComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: 'app-1' }) } },
        },
      ],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ApplicationDetailComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('loads the application and shows the job description', () => {
    http.expectOne('/api/applications/app-1').flush(APPLICATION);
    // The embedded CV panel loads this job's tailored CVs.
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);
    fixture.detectChanges();

    expect(component.application?.job_title).toBe('Backend Engineer');
    expect(component.notesDraft).toBe('Referred by Jo.');
    expect(component.appliedDateDraft).toBe('2026-02-02');

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Python, FastAPI, PostgreSQL.');
  });

  it('saves notes, retrospective and applied date', () => {
    http.expectOne('/api/applications/app-1').flush(APPLICATION);
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);

    component.notesDraft = 'Updated notes';
    component.lessonsDraft = 'Ask about on-call earlier.';
    component.save();

    const request = http.expectOne('/api/applications/app-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      notes: 'Updated notes',
      lessons_learned: 'Ask about on-call earlier.',
      applied_date: '2026-02-02',
    });
    request.flush({ ...APPLICATION, notes: 'Updated notes' });

    // The detail payload keeps its job description after the update.
    expect(component.application?.notes).toBe('Updated notes');
    expect(component.application?.job_description).toBe('Python, FastAPI, PostgreSQL.');
  });

  it('moves the application to another pipeline column', () => {
    http.expectOne('/api/applications/app-1').flush(APPLICATION);
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);

    component.changeStatus('interview');

    const request = http.expectOne('/api/applications/app-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ status: 'interview' });
    request.flush({ ...APPLICATION, status: 'interview' });

    expect(component.application?.status).toBe('interview');
  });

  it('deletes the application once confirmed', async () => {
    http.expectOne('/api/applications/app-1').flush(APPLICATION);
    http.expectOne((c) => c.url === '/api/cv/generated').flush([]);
    spyOn(TestBed.inject(ConfirmService), 'confirm').and.resolveTo(true);

    await component.remove();

    http
      .expectOne('/api/applications/app-1')
      .flush(null, { status: 204, statusText: 'No Content' });
  });

  it('reports a failed load', () => {
    http
      .expectOne('/api/applications/app-1')
      .flush({ detail: 'Application not found' }, { status: 404, statusText: 'Not Found' });

    expect(component.application).toBeNull();
    expect(component.error).toBe(component.i18n.t('errors.failedLoadApplication'));
  });
});
