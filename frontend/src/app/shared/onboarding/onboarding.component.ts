import { Component, EventEmitter, Output, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AppIconComponent } from '../icons/icon.component';
import { AppIconName } from '../icons/icon-name';
import { I18nService } from '../../services/i18n.service';

interface OnboardingStep {
  icon: AppIconName;
  titleKey: string;
  descriptionKey: string;
  route: string;
  ctaKey: string;
}

/**
 * First-run welcome panel. Shown on the Jobs page until the user dismisses it
 * (persisted in localStorage) or starts adding content.
 */
@Component({
  selector: 'app-onboarding',
  standalone: true,
  imports: [RouterLink, AppIconComponent],
  template: `
    <div class="onboarding panel">
      <header class="onboarding-head">
        <span class="onboarding-icon" aria-hidden="true">
          <app-icon name="sparkle" [size]="26" />
        </span>
        <div>
          <h2>{{ i18n.t('onboarding.welcome') }}</h2>
          <p>{{ i18n.t('onboarding.intro') }}</p>
        </div>
      </header>

      <ol class="onboarding-steps" role="list">
        @for (step of steps; track step.route) {
          <li class="onboarding-step">
            <span class="step-icon" aria-hidden="true">
              <app-icon [name]="step.icon" [size]="20" />
            </span>
            <div class="step-body">
              <h3>{{ i18n.t(step.titleKey) }}</h3>
              <p>{{ i18n.t(step.descriptionKey) }}</p>
            </div>
            <a class="btn btn-ghost btn-sm" [routerLink]="step.route" (click)="dismiss()">
              {{ i18n.t(step.ctaKey) }}
            </a>
          </li>
        }
      </ol>

      <footer class="onboarding-foot">
        <button type="button" class="btn btn-ghost" (click)="dismiss()">
          {{ i18n.t('onboarding.dismiss') }}
        </button>
      </footer>
    </div>
  `,
  styles: [
    `
      .onboarding {
        margin-bottom: var(--space-5);
        border-color: var(--color-border);
      }

      .onboarding-head {
        display: flex;
        align-items: center;
        gap: var(--space-4);
        margin-bottom: var(--space-4);

        .onboarding-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 52px;
          height: 52px;
          border-radius: var(--radius-full);
          background: var(--color-primary-soft);
          color: var(--color-primary);
          flex-shrink: 0;
        }

        h2 {
          margin: 0 0 2px;
          font-size: var(--text-xl);
          color: var(--color-primary);
        }

        p {
          margin: 0;
          color: var(--color-text-muted);
          font-size: var(--text-base);
        }
      }

      .onboarding-steps {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
      }

      .onboarding-step {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-3) var(--space-4);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        background: var(--color-surface-muted);

        .step-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 40px;
          height: 40px;
          border-radius: var(--radius-md);
          background: var(--color-surface);
          color: var(--color-accent);
          border: 1px solid var(--color-border);
          flex-shrink: 0;
        }

        .step-body {
          flex: 1;
          min-width: 0;

          h3 {
            margin: 0 0 2px;
            font-size: var(--text-base);
            color: var(--color-text);
          }

          p {
            margin: 0;
            font-size: var(--text-sm);
            color: var(--color-text-muted);
          }
        }
      }

      .onboarding-foot {
        display: flex;
        justify-content: flex-end;
        margin-top: var(--space-4);
      }

      @media (max-width: 640px) {
        .onboarding-step {
          flex-direction: column;
          align-items: flex-start;
        }
      }
    `,
  ],
})
export class OnboardingComponent {
  readonly i18n = inject(I18nService);

  @Output() dismissed = new EventEmitter<void>();

  readonly steps: OnboardingStep[] = [
    {
      icon: 'globe',
      titleKey: 'onboarding.step1.title',
      descriptionKey: 'onboarding.step1.description',
      route: '/sources',
      ctaKey: 'onboarding.step1.cta',
    },
    {
      icon: 'file-text',
      titleKey: 'onboarding.step2.title',
      descriptionKey: 'onboarding.step2.description',
      route: '/cv',
      ctaKey: 'onboarding.step2.cta',
    },
    {
      icon: 'kanban',
      titleKey: 'onboarding.step3.title',
      descriptionKey: 'onboarding.step3.description',
      route: '/applications',
      ctaKey: 'onboarding.step3.cta',
    },
  ];

  dismiss(): void {
    this.dismissed.emit();
  }
}
