import { Injectable } from '@angular/core';

import { AppIconName } from '../icons/icon-name';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  toasts: Toast[] = [];

  private nextId = 1;
  private timers = new Map<number, ReturnType<typeof setTimeout>>();

  private show(type: ToastType, message: string, duration = 4200): void {
    const toast: Toast = { id: this.nextId++, type, message };
    this.toasts.push(toast);
    this.scheduleDismiss(toast.id, duration);
  }

  success(message: string, duration = 3200): void {
    this.show('success', message, duration);
  }

  error(message: string, duration = 5000): void {
    this.show('error', message, duration);
  }

  warning(message: string, duration = 4200): void {
    this.show('warning', message, duration);
  }

  info(message: string, duration = 4200): void {
    this.show('info', message, duration);
  }

  dismiss(id: number): void {
    const timer = this.timers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
    this.toasts = this.toasts.filter((toast) => toast.id !== id);
  }

  private scheduleDismiss(id: number, duration: number): void {
    const timer = setTimeout(() => this.dismiss(id), duration);
    this.timers.set(id, timer);
  }

  iconFor(type: ToastType): AppIconName {
    switch (type) {
      case 'success':
        return 'circle-check';
      case 'error':
        return 'circle-alert';
      case 'warning':
        return 'triangle-alert';
      default:
        return 'info';
    }
  }
}
