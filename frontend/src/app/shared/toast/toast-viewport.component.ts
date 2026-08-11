import { Component } from '@angular/core';
import { NgFor } from '@angular/common';

import { AppIconComponent } from '../icons/icon.component';
import { ToastService } from './toast.service';

/**
 * Global toast viewport. Rendered once at the app root; toasts are fed in
 * through the ToastService. Accessible via role="status" (aria-live polite).
 */
@Component({
  selector: 'app-toast-viewport',
  standalone: true,
  imports: [NgFor, AppIconComponent],
  template: `
    <div class="toast-container" role="status" aria-live="polite">
      @for (toast of service.toasts; track toast.id) {
        <div class="toast" [class]="'toast-' + toast.type">
          <app-icon class="toast-icon" [name]="service.iconFor(toast.type)" [size]="18" />
          <div class="toast-body">{{ toast.message }}</div>
          <button
            type="button"
            class="toast-close"
            (click)="service.dismiss(toast.id)"
            aria-label="Dismiss notification"
          >
            <app-icon name="x" [size]="16" />
          </button>
        </div>
      }
    </div>
  `,
})
export class ToastViewportComponent {
  constructor(readonly service: ToastService) {}
}
