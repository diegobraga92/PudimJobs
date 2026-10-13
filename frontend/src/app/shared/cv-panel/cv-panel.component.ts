import { Component, Input, OnChanges, SimpleChanges, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import { AtsReport, CVStructure, CvService, GeneratedCV } from '../../services/cv.service';
import { ApplicationsService } from '../../services/applications.service';
import { JobsService } from '../../services/jobs.service';
import { I18nService } from '../../services/i18n.service';
import { AtsReportComponent } from '../ats-report/ats-report.component';
import { AppIconComponent } from '../icons/icon.component';
import { CvPreviewComponent } from '../cv-preview/cv-preview.component';
import { ConfirmService } from '../confirm/confirm.service';
import { ToastService } from '../toast/toast.service';

/**
 * Per-job tailored-CV workspace.
 *
 * Merges the two things that used to live apart on `/cv`: the tailored CV for
 * a job and its ATS check. Dropped into the application workspace
 * (`/applications/:id`), so "the CV I sent, and how it scores" sits next to the
 * application it belongs to.
 *
 * A job has up to two artifacts (ADR 016): the deterministic `rule` variant
 * (always produced, auto-linked to the application) and an optional `llm`
 * rewrite. Both are scored with the same deterministic scorer so they can be
 * compared; the user records which one was actually sent with *Use this one*.
 * Edits here target the artifact itself and never touch the master CV.
 *
 * Tailoring is asynchronous: `POST /api/jobs/{id}/tailor` returns 202 and a
 * Celery worker produces the artifacts, so enqueueing flips the panel into a
 * pending state the user resolves with "Refresh".
 */
@Component({
  selector: 'app-cv-panel',
  standalone: true,
  imports: [CommonModule, AppIconComponent, AtsReportComponent, CvPreviewComponent],
  templateUrl: './cv-panel.component.html',
  styleUrl: './cv-panel.component.scss',
})
export class CvPanelComponent implements OnChanges {
  readonly i18n = inject(I18nService);

  /** Job whose tailored CVs this panel manages. */
  @Input({ required: true }) jobId!: string;
  @Input() jobTitle = '';
  /** Set on the application workspace so a tailor run links back to it. */
  @Input() applicationId: string | null = null;
  /** `Application.generated_cv_id` — the artifact recorded as sent (badge). */
  @Input() linkedCvId: string | null = null;

  tailored: GeneratedCV[] = [];
  selectedId: string | null = null;
  report: AtsReport | null = null;
  loading = false;
  scoring = false;
  tailoring = false;
  saving = false;
  /** True between enqueueing a tailor run and the artifact appearing. */
  pending = false;
  error: string | null = null;

  /** Inline editor state — edits target the artifact, never the master CV. */
  editing = false;
  draft: CVStructure | null = null;
  draftSkills = '';

  constructor(
    private service: CvService,
    private jobs: JobsService,
    private applications: ApplicationsService,
    private toast: ToastService,
    private confirm: ConfirmService
  ) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['jobId'] && this.jobId) {
      this.load();
    }
  }

  get selected(): GeneratedCV | null {
    return this.tailored.find((item) => item.id === this.selectedId) ?? null;
  }

  /** Structured content behind the selection (drives the preview + ATS). */
  get selectedStructure(): CVStructure | null {
    return this.selected?.structured_json ?? null;
  }

  get previewName(): string {
    return this.selectedStructure?.full_name || 'Your Name';
  }

  /** Reload this job's tailored CVs, keeping the current selection if possible. */
  load(): void {
    this.loading = true;
    this.error = null;
    this.service.generated(this.jobId).subscribe({
      next: (items) => {
        this.loading = false;
        this.tailored = items;
        if (items.length > 0) {
          this.pending = false;
        }
        const stillThere = items.some((item) => item.id === this.selectedId);
        this.select(stillThere ? this.selectedId : (items[0]?.id ?? null));
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('errors.failedLoadTailoredCVs');
      },
    });
  }

  /** Switch the previewed/ATS-scored tailored version. */
  select(id: string | null): void {
    this.selectedId = id;
    // An in-progress inline edit belongs to the version being left behind.
    this.cancelEdit();
    this.report = this.selected?.ats_report ?? null;
  }

  isLinked(item: GeneratedCV): boolean {
    return !!this.linkedCvId && item.id === this.linkedCvId;
  }

  /** Human label for the variant that produced an artifact (ADR 016). */
  variantLabel(item: GeneratedCV): string {
    return this.i18n.t(item.variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule');
  }

  /**
   * Record this artifact as the one actually sent with the application.
   *
   * The worker auto-links only the deterministic variant, so this is how the
   * optional LLM rewrite becomes "the CV I sent" (ADR 016).
   */
  useThisOne(item: GeneratedCV): void {
    const applicationId = this.applicationId;
    if (!applicationId || this.isLinked(item)) {
      return;
    }
    this.applications.update(applicationId, { generated_cv_id: item.id }).subscribe({
      next: () => {
        this.linkedCvId = item.id;
        this.toast.success(this.i18n.t('cv.panel.sentRecorded'));
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateApplication');
        this.toast.error(this.i18n.t('errors.failedUpdateApplication'));
      },
    });
  }

  /** Open the inline editor seeded from the selected artifact's content. */
  startEdit(): void {
    const structure = this.selectedStructure;
    if (!structure) {
      return;
    }
    // Deep copy so a cancelled edit leaves the artifact untouched.
    this.draft = JSON.parse(JSON.stringify(structure)) as CVStructure;
    this.draftSkills = (this.draft.skills ?? []).join(', ');
    this.editing = true;
  }

  cancelEdit(): void {
    this.editing = false;
    this.draft = null;
    this.draftSkills = '';
  }

  updateDraftSummary(value: string): void {
    if (this.draft) {
      this.draft.summary = value;
    }
  }

  /** Bullets are edited as one-per-line text within an experience block. */
  updateDraftBullets(index: number, value: string): void {
    if (!this.draft) {
      return;
    }
    this.draft.experience[index].bullets = value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }

  bulletsText(item: { bullets: string[] }): string {
    return (item.bullets ?? []).join('\n');
  }

  /** Persist the inline edit; the artifact re-renders its PDF server-side. */
  saveEdit(): void {
    const item = this.selected;
    const draft = this.draft;
    if (!item || !draft || this.saving) {
      return;
    }
    draft.skills = this.draftSkills
      .split(',')
      .map((skill) => skill.trim())
      .filter(Boolean);
    this.saving = true;
    this.service.updateGenerated(item.id, draft).subscribe({
      next: (updated) => {
        this.saving = false;
        this.editing = false;
        this.draft = null;
        this.draftSkills = '';
        // Drop the now-stale ATS report with the content it scored.
        this.tailored = this.tailored.map((row) => (row.id === updated.id ? updated : row));
        this.report = updated.ats_report;
        this.toast.success(this.i18n.t('cv.panel.editSaved'));
      },
      error: () => {
        this.saving = false;
        this.error = this.i18n.t('errors.failedSaveCV');
        this.toast.error(this.i18n.t('errors.failedSaveCV'));
      },
    });
  }

  /** Enqueue a tailoring run for this job (linked to the application, if any). */
  tailor(): void {
    if (this.tailoring) {
      return;
    }
    this.tailoring = true;
    this.error = null;
    this.jobs.tailor(this.jobId, undefined, this.applicationId ?? undefined).subscribe({
      next: () => {
        this.tailoring = false;
        this.pending = true;
        this.toast.success(this.i18n.t('cv.panel.enqueued'));
      },
      error: () => {
        this.tailoring = false;
        this.error = this.i18n.t('errors.failedTailorCV');
      },
    });
  }

  /** Score the selected tailored CV against this job (cached on the artifact). */
  score(): void {
    const structure = this.selectedStructure;
    const item = this.selected;
    if (!structure || !item || this.scoring) {
      return;
    }
    this.scoring = true;
    this.service
      .atsScore({ cv: structure, job_id: this.jobId, generated_cv_id: item.id })
      .subscribe({
        next: (report) => {
          this.scoring = false;
          this.report = report;
          this.toast.success(
            this.i18n.t('cv.ats.scored', { score: report.score, method: report.method })
          );
          // The report is cached server-side — reload so the list badge updates.
          this.service.generated(this.jobId).subscribe({
            next: (items) => (this.tailored = items),
            error: () => undefined,
          });
        },
        error: () => {
          this.scoring = false;
          this.error = this.i18n.t('errors.failedAtsScore');
        },
      });
  }

  downloadPdf(item: GeneratedCV): void {
    this.service.downloadPdf(item.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `tailored-cv-${item.id}.pdf`;
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: () => (this.error = this.i18n.t('errors.failedDownloadPdf')),
    });
  }

  /** Delete a tailored CV after confirmation. */
  async remove(item: GeneratedCV): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('cv.deleteTailoredTitle'),
      message: this.i18n.t('cv.deleteTailoredMessage', {
        title: item.job_title ?? this.jobTitle,
      }),
      confirmLabel: this.i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.deleteGenerated(item.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('cv.tailoredDeleted'));
        if (this.selectedId === item.id) {
          this.selectedId = null;
        }
        this.load();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteGeneratedCV');
        this.toast.error(this.i18n.t('errors.failedDeleteGeneratedCV'));
      },
    });
  }

  atsScoreClass(score: number): string {
    if (score >= 75) {
      return 'badge-success';
    }
    return score >= 50 ? 'badge-warning' : 'badge-danger';
  }
}
