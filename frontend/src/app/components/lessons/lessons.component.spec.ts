import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { LessonEntry } from '../../services/applications.service';
import { I18nService } from '../../services/i18n.service';
import { LessonsComponent } from './lessons.component';

const LESSONS: LessonEntry[] = [
  {
    application_id: 'app-1',
    job_title: 'Backend Engineer',
    job_company: 'Acme',
    status: 'rejected',
    applied_date: '2026-01-10',
    lessons_learned: 'Study system design before the onsite.',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    application_id: 'app-2',
    job_title: 'Platform Engineer',
    job_company: 'Globex',
    status: 'interview',
    applied_date: null,
    lessons_learned: 'Send the follow-up email the same day.',
    updated_at: '2026-02-03T00:00:00Z',
  },
];

describe('LessonsComponent', () => {
  let fixture: ComponentFixture<LessonsComponent>;
  let component: LessonsComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LessonsComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(LessonsComponent);
    component = fixture.componentInstance;
    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('/api/applications/lessons').flush(LESSONS);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('renders every retrospective', () => {
    expect(component.lessons.length).toBe(2);
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Study system design before the onsite.');
    expect(text).toContain('Send the follow-up email the same day.');
  });

  it('filters by status', () => {
    component.setStatusFilter('interview');

    expect(component.visibleLessons.map((lesson) => lesson.application_id)).toEqual(['app-2']);
  });

  it('searches by job, company or text', () => {
    component.setQuery('globex');
    expect(component.visibleLessons.map((lesson) => lesson.application_id)).toEqual(['app-2']);

    component.setQuery('system design');
    expect(component.visibleLessons.map((lesson) => lesson.application_id)).toEqual(['app-1']);

    component.setQuery('');
    expect(component.visibleLessons.length).toBe(2);
  });

  it('shows the empty state when nothing matches', () => {
    component.setQuery('nothing matches this');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain(component.i18n.t('lessons.emptyTitle'));
  });
});
