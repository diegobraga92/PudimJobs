import { inject, Injectable, signal } from '@angular/core';

import { I18nService } from '../../services/i18n.service';

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Makes the confirm button destructive-styled. */
  destructive?: boolean;
}

export interface ConfirmState extends Required<ConfirmOptions> {
  visible: boolean;
  resolve: ((confirmed: boolean) => void) | null;
}

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  private readonly i18n = inject(I18nService);

  readonly state = signal<ConfirmState>({
    visible: false,
    title: 'Are you sure?',
    message: '',
    confirmLabel: 'Confirm',
    cancelLabel: 'Cancel',
    destructive: false,
    resolve: null,
  });

  /**
   * Opens a confirmation dialog and resolves the returned promise when the
   * user confirms or cancels. Replaces native window.confirm().
   */
  confirm(options: ConfirmOptions): Promise<boolean> {
    this.state.update((current) => ({
      ...current,
      title: options.title ?? this.i18n.t('confirm.areYouSure'),
      message: options.message,
      confirmLabel: options.confirmLabel ?? this.i18n.t('confirm.confirm'),
      cancelLabel: options.cancelLabel ?? this.i18n.t('confirm.cancel'),
      destructive: options.destructive ?? false,
      visible: true,
      resolve: null,
    }));
    return new Promise<boolean>((resolve) => {
      this.state.update((current) => ({ ...current, resolve }));
    });
  }

  close(confirmed: boolean): void {
    const resolve = this.state().resolve;
    this.state.update((current) => ({ ...current, visible: false }));
    resolve?.(confirmed);
  }
}
