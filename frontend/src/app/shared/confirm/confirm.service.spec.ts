import { Dialog } from '@angular/cdk/dialog';
import { ApplicationRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { I18nService } from '../../services/i18n.service';
import { ConfirmService } from './confirm.service';

/** The prompt's host element; CDK appends it to the overlay container in <body>. */
function dialogHost(): HTMLElement | null {
  return document.querySelector<HTMLElement>('app-confirm-dialog');
}

/** Buttons in render order: cancel first, then the confirm action. */
function dialogButtons(): HTMLButtonElement[] {
  return Array.from(dialogHost()?.querySelectorAll('button') ?? []);
}

/** Render the freshly opened overlay — the app does this on the next tick. */
function render(): void {
  TestBed.inject(ApplicationRef).tick();
}

describe('ConfirmService', () => {
  let service: ConfirmService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    TestBed.inject(I18nService).setLanguage('en');
    service = TestBed.inject(ConfirmService);
  });

  afterEach(() => {
    // Never leave a prompt behind for the next spec.
    service.close(false);
    TestBed.inject(Dialog).closeAll();
  });

  it('mounts the prompt synchronously, without waiting for a page change detection', () => {
    service.confirm({ message: 'Delete this application?' });

    // Regression: the prompt used to be mounted in the app shell and only
    // rendered on the *next* change detection pass, so a delete confirmed
    // right after an async action looked like it did nothing at all.
    expect(dialogHost()).withContext('dialog host in the DOM at once').toBeTruthy();

    render();
    expect(dialogHost()?.textContent).toContain('Delete this application?');
  });

  it('falls back to the localized defaults', () => {
    service.confirm({ message: 'Remove it?' });
    render();

    const text = dialogHost()?.textContent ?? '';
    expect(text).toContain('Are you sure?');
    expect(dialogButtons().map((button) => button.textContent?.trim())).toEqual([
      'Cancel',
      'Confirm',
    ]);
  });

  it('marks a destructive prompt', () => {
    service.confirm({ message: 'Delete it?', destructive: true });
    render();

    expect(dialogHost()?.querySelector('.confirm-icon.destructive')).toBeTruthy();
    expect(dialogButtons()[1].className).toContain('btn-danger-solid');
  });

  it('resolves true when the user confirms', async () => {
    const pending = service.confirm({ message: 'Delete it?' });
    render();

    dialogButtons()[1].click();

    await expectAsync(pending).toBeResolvedTo(true);
    expect(dialogHost()).toBeNull();
  });

  it('resolves false when the user cancels', async () => {
    const pending = service.confirm({ message: 'Delete it?' });
    render();

    dialogButtons()[0].click();

    await expectAsync(pending).toBeResolvedTo(false);
    expect(dialogHost()).toBeNull();
  });

  it('resolves false when the backdrop is clicked', async () => {
    const pending = service.confirm({ message: 'Delete it?' });
    render();

    const backdrop = document.querySelector<HTMLElement>('.cdk-overlay-backdrop');
    backdrop?.click();

    await expectAsync(pending).toBeResolvedTo(false);
  });

  it('resolves false when Escape is pressed', async () => {
    const pending = service.confirm({ message: 'Delete it?' });
    render();

    // CDK dispatches keydown from <body> and reads `keyCode`, which the
    // KeyboardEvent constructor cannot set.
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
    Object.defineProperty(escape, 'keyCode', { get: () => 27 });
    document.body.dispatchEvent(escape);

    await expectAsync(pending).toBeResolvedTo(false);
  });

  it('replaces an open prompt instead of stacking a second one', async () => {
    const first = service.confirm({ message: 'First question?' });
    const second = service.confirm({ message: 'Second question?' });

    // The stale prompt would otherwise never resolve its caller.
    await expectAsync(first).toBeResolvedTo(false);

    render();
    expect(document.querySelectorAll('app-confirm-dialog').length).toBe(1);
    expect(dialogHost()?.textContent).toContain('Second question?');

    service.close(true);
    await expectAsync(second).toBeResolvedTo(true);
  });

  it('closes programmatically so callers can bail out of a flow', async () => {
    const pending = service.confirm({ message: 'Delete it?' });

    service.close(false);

    await expectAsync(pending).toBeResolvedTo(false);
    // Closing when nothing is open must not throw (callers do it defensively).
    expect(() => service.close(true)).not.toThrow();
  });
});
