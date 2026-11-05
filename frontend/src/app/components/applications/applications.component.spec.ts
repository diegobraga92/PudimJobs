import { CdkDragDrop } from '@angular/cdk/drag-drop';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Application, ApplicationStatus } from '../../services/applications.service';
import { I18nService } from '../../services/i18n.service';
import { ApplicationsComponent } from './applications.component';

function application(id: string, status: ApplicationStatus, title: string): Application {
  return {
    id,
    job_id: `job-${id}`,
    status,
    applied_date: null,
    notes: null,
    lessons_learned: null,
    generated_cv_id: null,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    job_title: title,
    job_company: 'Acme',
    job_url: null,
  };
}

describe('ApplicationsComponent (kanban)', () => {
  let fixture: ComponentFixture<ApplicationsComponent>;
  let component: ApplicationsComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ApplicationsComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ApplicationsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  /** Loads one saved and one rejected application, then settles the board. */
  function load(): void {
    http
      .expectOne((c) => c.url === '/api/applications')
      .flush([application('a1', 'saved', 'Backend Engineer'), application('a2', 'rejected', 'Data Analyst')]);
    fixture.detectChanges();
  }

  /** Rendered columns (the header lives outside `.kanban`). */
  function columnCount(): number {
    return (fixture.nativeElement as HTMLElement).querySelectorAll('.column').length;
  }

  function card(index = 0): HTMLElement {
    return (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('.card')[index];
  }

  /** Press a card the way a drag gesture starts. */
  function pressCard(index = 0): void {
    card(index).dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
    fixture.detectChanges();
  }

  function release(): void {
    document.dispatchEvent(new MouseEvent('pointerup', { bubbles: true }));
    fixture.detectChanges();
  }

  it('hides the rejected column by default', () => {
    load();

    expect(columnCount()).toBe(4);
    expect(component.visibleStatuses).not.toContain('rejected');
    // The cards are still grouped by status, they are just not on screen.
    expect(component.columns.rejected.length).toBe(1);
  });

  it('shows the rejected column while the header toggle is ticked', () => {
    load();
    const toggle = (fixture.nativeElement as HTMLElement).querySelector(
      '.pipeline-toggle input',
    ) as HTMLInputElement;

    toggle.click();
    fixture.detectChanges();
    expect(toggle.checked).toBeTrue();
    expect(columnCount()).toBe(5);

    toggle.click();
    fixture.detectChanges();
    expect(columnCount()).toBe(4);
  });

  it('reveals the rejected column as soon as a card is pressed', () => {
    load();
    expect(columnCount()).toBe(4);

    // CDK caches the drop-list rects when the drag begins, so the column has to
    // be laid out before the first pointer move.
    pressCard();
    expect(component.dragging).toBeTrue();
    expect(columnCount()).toBe(5);
  });

  it('hides it again when the press did not become a drag', () => {
    load();

    pressCard();
    release();

    expect(columnCount()).toBe(4);
  });

  it('keeps it while a real drag is in flight', () => {
    load();

    pressCard();
    component.onDragStarted();
    release();
    // The drop resolves after pointerup; CDK reports the end of the drag next.
    expect(columnCount()).toBe(5);

    component.onDragEnded();
    fixture.detectChanges();
    expect(columnCount()).toBe(4);
  });

  it('keeps the column after a card is dropped into it', () => {
    load();
    const moved: CdkDragDrop<Application[]> = {
      previousContainer: { id: 'saved', data: component.columns.saved },
      container: { id: 'rejected', data: component.columns.rejected },
      previousIndex: 0,
      currentIndex: 1,
      item: { data: component.columns.saved[0] },
      isPointerOverContainer: true,
      distance: { x: 10, y: 10 },
      dropPoint: { x: 10, y: 10 },
      event: new MouseEvent('mouseup'),
    } as unknown as CdkDragDrop<Application[]>;

    component.onDrop(moved);
    http
      .expectOne((c) => c.method === 'PUT' && c.url === '/api/applications/a1')
      .flush({ ...application('a1', 'rejected', 'Backend Engineer') });
    fixture.detectChanges();

    expect(component.columns.rejected.length).toBe(2);
    expect(component.visibleStatuses).toContain('rejected');
    expect(columnCount()).toBe(5);
  });
});
