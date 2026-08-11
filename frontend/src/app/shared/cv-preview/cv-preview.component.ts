import { Component, Input } from '@angular/core';

import { CVStructure } from '../../services/cv.service';

/**
 * Renders a CVStructure as a clean, A4-style single-page document. Used by the
 * CV editor's "Preview" tab for a live, WYSIWYG look at the resume.
 */
@Component({
  selector: 'app-cv-preview',
  standalone: true,
  template: `
    <div class="cv-preview-sheet">
      <header class="cv-head">
        <h2>Alex Johnson</h2>
        <p class="cv-contact">
          @if (cv.summary) {
            <span>{{ cv.summary }}</span>
          } @else {
            <span class="empty">Your professional summary appears here.</span>
          }
        </p>
      </header>

      @if (cv.skills.length > 0) {
        <section class="cv-section">
          <h3>Skills</h3>
          <div class="cv-skills">
            @for (skill of cv.skills; track skill) {
              <span class="skill-chip">{{ skill }}</span>
            }
          </div>
        </section>
      }

      @if (cv.experience.length > 0) {
        <section class="cv-section">
          <h3>Experience</h3>
          @for (exp of cv.experience; track $index) {
            <div class="cv-entry">
              <div class="cv-entry-head">
                <strong>{{ exp.title }}</strong>
                <span class="cv-dates">{{ formatDates(exp.start_date, exp.end_date) }}</span>
              </div>
              <div class="cv-entry-sub">{{ exp.company }}</div>
              @if (exp.bullets.length > 0) {
                <ul class="cv-bullets">
                  @for (bullet of exp.bullets; track bullet) {
                    <li>{{ bullet }}</li>
                  }
                </ul>
              }
            </div>
          }
        </section>
      }

      @if (cv.education.length > 0) {
        <section class="cv-section">
          <h3>Education</h3>
          @for (edu of cv.education; track $index) {
            <div class="cv-entry">
              <div class="cv-entry-head">
                <strong>{{ edu.degree }}</strong>
                <span class="cv-dates">{{ edu.year }}</span>
              </div>
              <div class="cv-entry-sub">{{ edu.institution }}</div>
            </div>
          }
        </section>
      }

      @if (cv.projects.length > 0) {
        <section class="cv-section">
          <h3>Projects</h3>
          @for (project of cv.projects; track $index) {
            <div class="cv-entry">
              <div class="cv-entry-head">
                <strong>{{ project.name }}</strong>
                @if (project.link) {
                  <span class="cv-dates">{{ project.link }}</span>
                }
              </div>
              @if (project.description) {
                <p class="cv-desc">{{ project.description }}</p>
              }
            </div>
          }
        </section>
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
        background: var(--color-surface-muted);
        border-radius: var(--radius-lg);
        padding: var(--space-6);
      }

      .cv-preview-sheet {
        max-width: 640px;
        margin: 0 auto;
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 2.5rem 2.75rem;
        box-shadow: var(--shadow-md);
      }

      .cv-head h2 {
        margin: 0 0 var(--space-1);
        font-size: 1.6rem;
        color: var(--color-primary);
        letter-spacing: 0.01em;
      }

      .cv-contact {
        margin: 0;
        color: var(--color-text-secondary);
        font-size: var(--text-base);
        line-height: 1.5;

        .empty {
          color: var(--color-text-faint);
          font-style: italic;
        }
      }

      .cv-section {
        margin-top: var(--space-5);
        padding-top: var(--space-4);
        border-top: 1px solid var(--color-border);

        h3 {
          margin: 0 0 var(--space-3);
          font-size: var(--text-sm);
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--color-accent);
        }
      }

      .cv-skills {
        display: flex;
        flex-wrap: wrap;
        gap: var(--space-2);
      }

      .skill-chip {
        padding: 0.15rem 0.6rem;
        border: 1px solid var(--color-border-strong);
        border-radius: var(--radius-full);
        font-size: var(--text-xs);
        color: var(--color-text-secondary);
      }

      .cv-entry {
        margin-bottom: var(--space-4);

        &:last-child {
          margin-bottom: 0;
        }
      }

      .cv-entry-head {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: var(--space-3);
      }

      .cv-entry-sub {
        color: var(--color-text-secondary);
        font-size: var(--text-sm);
        margin-top: 1px;
      }

      .cv-dates {
        color: var(--color-text-muted);
        font-size: var(--text-xs);
        white-space: nowrap;
      }

      .cv-bullets {
        margin: var(--space-2) 0 0;
        padding-left: 1.1rem;
        color: var(--color-text);
        font-size: var(--text-sm);
        line-height: 1.5;
      }

      .cv-desc {
        margin: var(--space-1) 0 0;
        color: var(--color-text);
        font-size: var(--text-sm);
        line-height: 1.5;
      }

      @media (max-width: 768px) {
        :host {
          padding: var(--space-3);
        }
        .cv-preview-sheet {
          padding: var(--space-5);
        }
      }
    `,
  ],
})
export class CvPreviewComponent {
  @Input({ required: true }) cv!: CVStructure;

  formatDates(start: string | null, end: string | null): string {
    if (!start && !end) {
      return '—';
    }
    if (start && end) {
      return `${this.fmtMonth(start)} — ${this.fmtMonth(end)}`;
    }
    return this.fmtMonth(start || end || '');
  }

  private fmtMonth(value: string): string {
    const [year, month] = value.split('-');
    if (!year) {
      return value;
    }
    if (!month) {
      return year;
    }
    const names = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return `${names[Number(month) - 1] ?? month} ${year}`;
  }
}
