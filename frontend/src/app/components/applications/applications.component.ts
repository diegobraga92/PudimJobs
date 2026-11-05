import { Component, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CdkDragDrop, DragDropModule, moveItemInArray, transferArrayItem } from '@angular/cdk/drag-drop';

import {
  Application,
  ApplicationStatus,
  ApplicationsService,
} from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];
/** Columns shown until the user asks for the rejected one (or starts dragging a card). */
const VISIBLE_STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer'];

/** Application pipeline (kanban). */
@Component({
  selector: 'app-applications',
  standalone: true,
  imports: [CommonModule, DragDropModule, AppIconComponent],
  templateUrl: './applications.component.html',
  styleUrl: './applications.component.scss',
})
export class ApplicationsComponent implements OnInit {
  columns: Record<ApplicationStatus, Application[]> = {
    saved: [],
    applied: [],
    interview: [],
    offer: [],
    rejected: [],
  };
  statuses = STATUSES;
  error: string | null = null;
  total = 0;
  /**
   * Rejected applications are hidden from the board by default: that column is
   * history, not work in progress. It can be pinned on with the header toggle
   * and it appears on its own while a card is being dragged, so a card can
   * still be dropped into it.
   */
  showRejected = false;
  /** True from pressing a card until the end of the press (drag or plain click). */
  dragging = false;
  /** True while CDK is actually moving a card, from the first moved pixel to the drop. */
  dragActive = false;

  /** The columns the board renders right now. */
  get visibleStatuses(): ApplicationStatus[] {
    return this.showRejected || this.dragging ? this.statuses : VISIBLE_STATUSES;
  }

  constructor(
    private service: ApplicationsService,
    private router: Router,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  statusLabel(status: ApplicationStatus): string {
    return this.i18n.t(`pipeline.${status}`);
  }

  /** Open the application workspace for a card. */
  openWorkspace(application: Application): void {
    this.dragging = false;
    this.router.navigate(['/applications', application.id]);
  }

  toggleRejected(): void {
    this.showRejected = !this.showRejected;
  }

  /**
   * Reveal the rejected column as soon as a card is pressed. CDK measures and
   * caches every drop list's rect when the drag starts (on the first pointer
   * move), so the column has to be laid out *before* that — revealing it on
   * `cdkDragStarted` would be one change detection too late and it could never
   * receive the card.
   */
  onCardPointerDown(event: PointerEvent): void {
    if (event.button === 0) {
      this.dragging = true;
    }
  }

  /** CDK took over the press and is moving a card. */
  onDragStarted(): void {
    this.dragActive = true;
  }

  /** The drag finished: hide the column again unless it was pinned or received the card. */
  onDragEnded(): void {
    this.dragActive = false;
    this.dragging = false;
  }

  /**
   * A press that never turned into a drag must not leave the column showing.
   * During a real drag `dragActive` is already true here, so the column stays
   * until `cdkDragEnded` — the drop is resolved a moment after pointerup.
   */
  @HostListener('document:pointerup')
  @HostListener('document:pointercancel')
  onPointerReleased(): void {
    if (!this.dragActive) {
      this.dragging = false;
    }
  }

  /** Move a card between pipeline columns, persist the new status and revert on error. */
  onDrop(event: CdkDragDrop<Application[]>): void {
    if (event.previousContainer === event.container) {
      // Intra-column reorder — visual only, not persisted.
      moveItemInArray(event.container.data, event.previousIndex, event.currentIndex);
      this.dragging = false;
      return;
    }
    const application = event.item.data as Application;
    const targetStatus = event.container.id as ApplicationStatus;

    transferArrayItem(
      event.previousContainer.data,
      event.container.data,
      event.previousIndex,
      event.currentIndex,
    );
    application.status = targetStatus;
    this.dragging = false;
    // Keep the column on screen after a drop into it, so the card doesn't vanish.
    this.showRejected = this.showRejected || targetStatus === 'rejected';

    this.service.update(application.id, { status: targetStatus }).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('applications.movedTo', { status: this.i18n.t(`pipeline.${targetStatus}`) }));
      },
      error: () => {
        this.toast.error(this.i18n.t('errors.failedMoveApplication'));
        this.refresh();
      },
    });
  }

  refresh(): void {
    this.error = null;
    this.service.list().subscribe({
      next: (applications) => {
        for (const status of STATUSES) {
          this.columns[status] = [];
        }
        this.total = applications.length;
        for (const application of applications) {
          this.columns[application.status].push(application);
        }
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadApplications');
        this.toast.error(this.i18n.t('errors.failedLoadApplications'));
      },
    });
  }
}
