import { Component } from '@angular/core';
import { TestBed, ComponentFixture } from '@angular/core/testing';

import { I18nService } from '../../services/i18n.service';
import { AppModalComponent } from './modal.component';

@Component({
  standalone: true,
  imports: [AppModalComponent],
  template: `
    <app-modal [title]="title" (closed)="closes = closes + 1">
      <form class="form">
        <input id="host-field" class="input" />
        <div class="form-actions"><button type="submit" class="btn btn-primary">Save</button></div>
      </form>
    </app-modal>
  `,
})
class ModalHostComponent {
  title = 'Edit source';
  closes = 0;
}

describe('AppModalComponent', () => {
  let fixture: ComponentFixture<ModalHostComponent>;
  let host: ModalHostComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ModalHostComponent] }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    fixture = TestBed.createComponent(ModalHostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the title, the close button and the projected form', () => {
    const element = fixture.nativeElement as HTMLElement;
    const title = element.querySelector<HTMLElement>('.modal-head h3');

    expect(title?.textContent).toContain('Edit source');
    expect(element.querySelector('.modal-close')).toBeTruthy();
    expect(element.querySelector('.form #host-field')).toBeTruthy();
    expect(element.querySelector('.form-actions .btn-primary')?.textContent).toContain('Save');
  });

  it('labels the dialog with the rendered title', () => {
    const element = fixture.nativeElement as HTMLElement;
    const dialog = element.querySelector<HTMLElement>('.modal');
    const title = element.querySelector<HTMLElement>('.modal-head h3');

    expect(dialog?.getAttribute('role')).toBe('dialog');
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(dialog?.getAttribute('aria-labelledby')).toBe(title?.id);
  });

  it('applies the large width modifier only when requested', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.modal')?.classList).not.toContain('modal-lg');

    const modal = fixture.debugElement.query((node) => node.name === 'app-modal');
    modal.componentInstance.size = 'lg';
    fixture.detectChanges();

    expect(element.querySelector('.modal')?.classList).toContain('modal-lg');
  });

  it('emits closed when the backdrop is clicked', () => {
    const element = fixture.nativeElement as HTMLElement;

    element.querySelector<HTMLElement>('.modal-backdrop')?.click();
    fixture.detectChanges();

    expect(host.closes).toBe(1);
  });

  it('emits closed when the header close button is clicked', () => {
    const element = fixture.nativeElement as HTMLElement;

    element.querySelector<HTMLButtonElement>('.modal-close')?.click();
    fixture.detectChanges();

    expect(host.closes).toBe(1);
  });

  it('emits closed on Escape', () => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();

    expect(host.closes).toBe(1);
  });

  it('does not emit closed when clicking inside the dialog', () => {
    const element = fixture.nativeElement as HTMLElement;

    element.querySelector<HTMLElement>('.modal-head h3')?.click();
    element.querySelector<HTMLInputElement>('#host-field')?.click();
    fixture.detectChanges();

    expect(host.closes).toBe(0);
  });
});
