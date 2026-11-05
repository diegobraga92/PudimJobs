import { Dialog, DialogRef } from '@angular/cdk/dialog';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { I18nService } from '../../services/i18n.service';
import { ConfirmDialogComponent, ConfirmDialogData } from './confirm-dialog.component';

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Makes the confirm button destructive-styled. */
  destructive?: boolean;
}

/**
 * Asks the user to confirm a destructive action. The prompt is opened in a CDK
 * overlay rather than rendered inside the app shell: an overlay is created
 * immediately, from any code path, so it shows up even when the caller is an
 * async handler that just finished and may navigate away right after.
 */
@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly i18n = inject(I18nService);
  private readonly dialog = inject(Dialog);

  /** The prompt on screen, if any. A second `confirm()` dismisses it. */
  private open: DialogRef<boolean> | null = null;

  /** Opens a confirmation dialog and resolves the returned promise when the user confirms or cancels. Replaces native window.confirm(). */
  confirm(options: ConfirmOptions): Promise<boolean> {
    // Only one prompt at a time: an overlapping call cancels the previous one
    // instead of leaving its promise pending forever.
    this.close(false);

    const ref = this.dialog.open<boolean, ConfirmDialogData>(ConfirmDialogComponent, {
      data: {
        title: options.title ?? this.i18n.t('confirm.areYouSure'),
        message: options.message,
        confirmLabel: options.confirmLabel ?? this.i18n.t('confirm.confirm'),
        cancelLabel: options.cancelLabel ?? this.i18n.t('confirm.cancel'),
        destructive: options.destructive ?? false,
      },
      role: 'alertdialog',
      ariaLabelledBy: 'confirm-title',
      ariaDescribedBy: 'confirm-message',
      // Reuses the app's modal backdrop/panel styles; CDK adds the centering
      // wrapper, the focus trap and the Escape/backdrop dismissal.
      backdropClass: 'modal-backdrop',
      panelClass: 'confirm-pane',
      hasBackdrop: true,
      disableClose: false,
      // Focusing the first button keeps Enter on "Cancel", never on the
      // destructive action.
      autoFocus: 'first-tabbable',
      restoreFocus: true,
    });

    this.open = ref;
    // Backdrop clicks and Escape close the dialog without a value: treat
    // anything that is not a `true` as a cancel.
    return firstValueFrom(ref.closed, { defaultValue: false }).then((confirmed) => {
      if (this.open === ref) {
        this.open = null;
      }
      return confirmed === true;
    });
  }

  /** Dismisses the prompt programmatically; `confirmed` decides the pending promise. */
  close(confirmed: boolean): void {
    const ref = this.open;
    this.open = null;
    ref?.close(confirmed);
  }
}

