import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { ConfirmService } from '../../shared/confirm/confirm.service';
import { PrepTask } from '../../services/prep-tasks.service';
import { I18nService } from '../../services/i18n.service';
import { PrepTasksComponent } from './prep-tasks.component';

function prepTask(overrides: Partial<PrepTask> = {}): PrepTask {
  return {
    id: 'task-1',
    title: 'Rehearse the system-design round',
    category: 'technical',
    status: 'pending',
    due_date: '2026-03-01',
    notes: null,
    job_id: null,
    application_id: null,
    job_title: null,
    job_company: null,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    ...overrides,
  };
}

describe('PrepTasksComponent', () => {
  let fixture: ComponentFixture<PrepTasksComponent>;
  let component: PrepTasksComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PrepTasksComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(PrepTasksComponent);
    component = fixture.componentInstance;
    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function flushTasks(tasks: PrepTask[] = [prepTask()]): void {
    http.expectOne('/api/jobs').flush([]);
    http
      .expectOne('/api/applications')
      .flush([
        {
          id: 'app-1',
          job_id: 'job-1',
          status: 'interview',
          applied_date: '2026-02-10',
          notes: null,
          lessons_learned: null,
          cv_version: null,
          created_at: '2026-02-01T00:00:00Z',
          updated_at: '2026-02-01T00:00:00Z',
          job_title: 'Backend Engineer',
          job_company: 'Acme',
          job_url: null,
        },
      ]);
    http.expectOne('/api/prep-tasks').flush(tasks);
  }

  it('lists prep tasks and reports the pending/done counters', () => {
    flushTasks([prepTask(), prepTask({ id: 'task-2', status: 'done', title: 'Research the team' })]);
    fixture.detectChanges();

    expect(component.tasks.length).toBe(2);
    expect(component.pendingCount).toBe(1);
    expect(component.doneCount).toBe(1);

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Rehearse the system-design round');
    expect(text).toContain('Research the team');
  });

  it('creates a task from the form', () => {
    flushTasks([]);

    component.openCreate();
    component.taskForm.setValue({
      title: 'Mock interview',
      category: 'behavioral',
      status: 'pending',
      due_date: '2026-03-05',
      job_id: '',
      application_id: 'app-1',
      notes: 'Ask a friend',
    });
    component.save();

    const request = http.expectOne('/api/prep-tasks');
    expect(request.request.method).toBe('POST');
    expect(request.request.body.title).toBe('Mock interview');
    expect(request.request.body.category).toBe('behavioral');
    expect(request.request.body.due_date).toBe('2026-03-05');
    expect(request.request.body.job_id).toBeNull();
    expect(request.request.body.application_id).toBe('app-1');
    request.flush(prepTask({ id: 'task-9', title: 'Mock interview' }));

    http.expectOne('/api/prep-tasks').flush([]);
    expect(component.showForm).toBeFalse();
  });

  it('labels a task linked to a pipeline application', () => {
    flushTasks([prepTask({ application_id: 'app-1' })]);
    fixture.detectChanges();

    expect(component.applicationLabel('app-1')).toBe('Backend Engineer — Acme');
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Backend Engineer — Acme');
  });

  it('cycles a task through its statuses', () => {
    flushTasks();

    component.cycleStatus(prepTask());

    const request = http.expectOne('/api/prep-tasks/task-1');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ status: 'in_progress' });
    request.flush(prepTask({ status: 'in_progress' }));

    http.expectOne('/api/prep-tasks').flush([prepTask({ status: 'in_progress' })]);
    expect(component.tasks[0].status).toBe('in_progress');
  });

  it('passes status and job filters to the API', () => {
    flushTasks();

    component.setStatusFilter('done');
    http.expectOne((request) => request.url === '/api/prep-tasks' && request.params.get('status_filter') === 'done').flush([]);

    component.jobFilter = 'job-7';
    component.refresh();
    http
      .expectOne(
        (request) =>
          request.url === '/api/prep-tasks' &&
          request.params.get('status_filter') === 'done' &&
          request.params.get('job_id') === 'job-7'
      )
      .flush([]);

    expect(component.jobFilter).toBe('job-7');
    expect(component.statusFilter).toBe('done');
  });

  it('deletes a task after confirmation', async () => {
    flushTasks();
    const confirm = TestBed.inject(ConfirmService);

    const pending = component.remove(prepTask());
    confirm.close(true);
    await pending;

    const request = http.expectOne('/api/prep-tasks/task-1');
    expect(request.request.method).toBe('DELETE');
    request.flush(null);

    http.expectOne('/api/prep-tasks').flush([]);
    expect(component.tasks.length).toBe(0);
  });

  it('keeps the task when the confirmation is dismissed', async () => {
    flushTasks();
    const confirm = TestBed.inject(ConfirmService);

    const pending = component.remove(prepTask());
    confirm.close(false);
    await pending;

    http.expectNone('/api/prep-tasks/task-1');
    expect(component.tasks.length).toBe(1);
  });
});
