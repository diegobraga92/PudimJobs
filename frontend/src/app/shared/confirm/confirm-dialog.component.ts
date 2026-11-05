import { DIALOG_DATA, DialogRef } from '@angular/cdk/dialog';
import { Component, Inject } from '@angular/core';

import { AppIconComponent } from '../icons/icon.component';

/** What the prompt renders; `ConfirmService` fills in the localized defaults. */
export interface ConfirmDialogData {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  destructive: boolean;
}

/**
 * Confirmation prompt (role="alertdialog"). `ConfirmService` opens it through
 * the CDK dialog overlay, so it lives outside the routed view tree and paints
 * on top of whatever page is open — including a page that just finished an
 * async action. CDK supplies the backdrop, the focus trap, Escape and focus
 * restoration; closing with `true` confirms, anything else cancels.
 */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [AppIconComponent],
  template: `
    <div class="modal confirm-modal">
      <div class="confirm-icon" [class.destructive]="data.destructive">
        <app-icon name="triangle-alert" [size]="24" />
      </div>
      <div class="confirm-body">
        <h3 id="confirm-title">{{ data.title }}</h3>
        <p id="confirm-message">{{ data.message }}</p>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" (click)="ref.close(false)">
          {{ data.cancelLabel }}
        </button>
        <button
          type="button"
          [class]="data.destructive ? 'btn btn-danger-solid' : 'btn btn-primary'"
          (click)="ref.close(true)"
        >
          {{ data.confirmLabel }}
        </button>
      </div>
    </div>
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
  constructor(
    @Inject(DIALOG_DATA) readonly data: ConfirmDialogData,
    readonly ref: DialogRef<boolean>,
  ) {}
}
