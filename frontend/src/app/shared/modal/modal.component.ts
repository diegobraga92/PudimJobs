import { Component, EventEmitter, HostListener, Input, Output, inject } from '@angular/core';

import { I18nService } from '../../services/i18n.service';
import { AppIconComponent } from '../icons/icon.component';

let modalSequence = 0;

/**
 * Shared modal shell for create/edit forms and other transient panels.
 *
 * Renders over the page (fixed backdrop) instead of pushing the page content down, reusing the
 * global `.modal-backdrop` / `.modal` styles. Every dismiss path — the backdrop, the header X and
 * Escape — emits `closed`, so the host component can reset its form state.
 *
 * Projected content is the body: hosts keep declaring their own `<form>` (with `.form-actions`).
 */
@Component({
  selector: 'app-modal',
  standalone: true,
  imports: [AppIconComponent],
  template: `
    <div class="modal-backdrop" (click)="closed.emit()">
      <div
        class="modal"
        [class.modal-lg]="size === 'lg'"
        role="dialog"
        aria-modal="true"
        [attr.aria-labelledby]="titleId"
        (click)="$event.stopPropagation()"
      >
        <header class="modal-head">
          <h3 [id]="titleId">{{ title }}</h3>
          <button
            type="button"
            class="btn btn-ghost btn-sm modal-close"
            [attr.aria-label]="i18n.t('common.close')"
            (click)="closed.emit()"
          >
            <app-icon name="x" [size]="16" />
          </button>
        </header>

        <ng-content />
      </div>
    </div>
  `,
  styles: [
    `
      .modal-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: var(--space-3);
      }

      .modal-close {
        flex-shrink: 0;
        padding: 0.3rem;
        line-height: 1;
      }

      .modal-lg {
        width: min(720px, 94vw);
      }
    `,
  ],
})
export class AppModalComponent {
  /** Dialog title, also used as the accessible name via `aria-labelledby`. */
  @Input() title = '';

  /** `md` (default) is a compact dialog, `lg` gives form-heavy dialogs more room. */
  @Input() size: 'md' | 'lg' = 'md';

  @Output() readonly closed = new EventEmitter<void>();

  readonly i18n = inject(I18nService);

  readonly titleId = `app-modal-title-${++modalSequence}`;

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closed.emit();
  }
}
