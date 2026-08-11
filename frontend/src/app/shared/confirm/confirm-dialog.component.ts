import { Component, HostListener } from '@angular/core';

import { AppIconComponent } from '../icons/icon.component';
import { ConfirmService } from './confirm.service';

/**
 * Accessible confirmation dialog (role="dialog", Escape to cancel,
 * focus stays within the modal via inert backdrop behavior).
 */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [AppIconComponent],
  template: `
    @if (service.state().visible) {
      <div class="modal-backdrop" (click)="service.close(false)">
        <div
          class="modal confirm-modal"
          role="alertdialog"
          aria-modal="true"
          [attr.aria-labelledby]="'confirm-title'"
          (click)="$event.stopPropagation()"
        >
          <div class="confirm-icon" [class.destructive]="service.state().destructive">
            <app-icon name="triangle-alert" [size]="24" />
          </div>
          <div class="confirm-body">
            <h3 id="confirm-title">{{ service.state().title }}</h3>
            <p>{{ service.state().message }}</p>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn btn-ghost" (click)="service.close(false)">
              {{ service.state().cancelLabel }}
            </button>
            <button
              type="button"
              [class]="service.state().destructive ? 'btn btn-danger-solid' : 'btn btn-primary'"
              (click)="service.close(true)"
            >
              {{ service.state().confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [
    `
      .confirm-modal {
        align-items: flex-start;
      }
      .confirm-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 44px;
        height: 44px;
        border-radius: var(--radius-full);
        background: var(--color-warning-soft);
        color: var(--color-warning);
        flex-shrink: 0;

        &.destructive {
          background: var(--color-danger-soft);
          color: var(--color-danger);
        }
      }
      .confirm-body {
        flex: 1;
      }
      .confirm-body p {
        margin: 0;
        color: var(--color-text-muted);
        font-size: var(--text-base);
      }
    `,
  ],
})
export class ConfirmDialogComponent {
  constructor(readonly service: ConfirmService) {}

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.service.state().visible) {
      this.service.close(false);
    }
  }
}
