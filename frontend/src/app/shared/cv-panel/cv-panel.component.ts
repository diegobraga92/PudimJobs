import { Component, Input, OnChanges, OnDestroy, SimpleChanges, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription, interval } from 'rxjs';

import { AtsReport, CVStructure, CvService, CvVariant, GeneratedCV } from '../../services/cv.service';
import { ApplicationsService } from '../../services/applications.service';
import { JobsService } from '../../services/jobs.service';
import { I18nService } from '../../services/i18n.service';
import { AtsReportComponent } from '../ats-report/ats-report.component';
import { AppIconComponent } from '../icons/icon.component';
import { CvPreviewComponent } from '../cv-preview/cv-preview.component';
import { ConfirmService } from '../confirm/confirm.service';
import { ToastService } from '../toast/toast.service';

/** How often the panel re-checks for a freshly queued artifact while a tailor run is in flight. */
export const POLL_INTERVAL_MS = 3000;
/** Give up after ~90s of polling. A long or stuck job must not leave the panel hammering the API forever; the manual *Refresh* button stays as the fallback. */
export const POLL_MAX_TICKS = 30;

/** Per-job tailored-CV workspace. */
@Component({
  selector: 'app-cv-panel',
  standalone: true,
  imports: [CommonModule, AppIconComponent, AtsReportComponent, CvPreviewComponent],
  templateUrl: './cv-panel.component.html',
  styleUrl: './cv-panel.component.scss',
})
export class CvPanelComponent implements OnChanges, OnDestroy {
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

  /** Auto-refresh handle used while a tailor run is in flight. */
  private poll?: Subscription;
  /** Ticks spent waiting for the worker; see {@link POLL_MAX_TICKS}. */
  private pollTicks = 0;
  /**
   * Variants the in-flight run will produce (`rule` always, plus `llm` when the
   * LLM is enabled), as advertised by the enqueue response. Polling keeps going
   * until every one has landed, so the slow AI rewrite is picked up without a
   * manual *Refresh*. `null` means "any artifact settles the run" (a manual
   * reload, or a run queued elsewhere).
   */
  private expectedVariants: CvVariant[] | null = null;

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

  ngOnDestroy(): void {
    this.stopPolling();
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

  /** True when an artifact actually carries CV content. */
  hasContent(item: GeneratedCV): boolean {
    return !!item.structured_json;
  }

  /** Only the deterministic variant exists, so the AI rewrite was skipped server-side (the LLM is disabled in Admin → LLM, or no API key is stored). */
  get llmVariantMissing(): boolean {
    if (this.pending) {
      // Still waiting on the run: the AI rewrite may simply not have landed yet.
      return false;
    }
    const only = this.tailored.length === 1 ? this.tailored[0] : null;
    return !!only && only.variant === 'rule' && this.hasContent(only);
  }

  /** Reload this job's tailored CVs, keeping the current selection if possible. */
  load(): void {
    this.loading = true;
    this.error = null;
    // A manual reload is the fallback for a run we are no longer tracking.
    this.expectedVariants = null;
    this.service.generated(this.jobId).subscribe({
      next: (items) => {
        this.loading = false;
        this.applyLoaded(items);
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('errors.failedLoadTailoredCVs');
      },
    });
  }

  /** Store this job's artifacts, dropping content-less ones. */
  private setTailored(items: GeneratedCV[]): void {
    this.tailored = items.filter((item) => this.hasContent(item));
  }

  /** Keep the current selection when it survived the reload, else fall back to the newest artifact. */
  private selectFrom(usable: GeneratedCV[]): void {
    const stillThere = usable.some((item) => item.id === this.selectedId);
    this.select(stillThere ? this.selectedId : (usable[0]?.id ?? null));
  }

  /** Apply a freshly fetched list: resolve the pending state once an artifact exists, and keep the current selection when it is still there. */
  private applyLoaded(items: GeneratedCV[]): void {
    this.setTailored(items);
    const usable = this.tailored;
    this.selectFrom(usable);
    if (usable.length > 0) {
      this.pending = false;
      this.stopPolling();
    }
  }

  /**
   * Apply a polled list: refresh what the panel shows, but only settle once the
   * run is done. The worker commits the deterministic variant before the slow AI
   * rewrite (ADR 016), so stopping at the first artifact would strand the panel on
   * the deterministic CV and force a manual *Refresh*.
   */
  private applyPolled(items: GeneratedCV[]): void {
    this.setTailored(items);
    const usable = this.tailored;
    this.selectFrom(usable);
    if (this.runSettled(usable)) {
      this.pending = false;
      this.expectedVariants = null;
      this.stopPolling();
    }
  }

  /** True when every awaited variant is present; without an expected set, any artifact settles the run. */
  private runSettled(usable: GeneratedCV[]): boolean {
    const expected = this.expectedVariants;
    if (!expected) {
      return usable.length > 0;
    }
    return expected.every((variant) => usable.some((item) => item.variant === variant));
  }

  /** Watch for the artifacts a queued tailor run will produce. */
  private startWatching(): void {
    this.stopPolling();
    this.pollTicks = 0;
    this.poll = interval(POLL_INTERVAL_MS).subscribe(() => {
      this.pollTicks += 1;
      if (this.pollTicks > POLL_MAX_TICKS) {
        this.stopPolling();
        return;
      }
      this.service.generated(this.jobId).subscribe({
        next: (items) => this.applyPolled(items),
        // A failed poll must not replace the pending notice with an error.
        error: () => undefined,
      });
    });
  }

  private stopPolling(): void {
    this.poll?.unsubscribe();
    this.poll = undefined;
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

  /** Record this artifact as the one actually sent with the application. */
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
      next: (result) => {
        this.tailoring = false;
        this.pending = true;
        // Wait for every variant the run will produce. The worker commits the
        // deterministic one first and the AI rewrite later (ADR 016), so the
        // enqueue response — not the first artifact to appear — defines "done".
        this.expectedVariants = result.variants ?? null;
        // Resolve the pending state on its own instead of asking the user to
        // keep clicking *Refresh* while the Celery worker runs.
        if (!this.runSettled(this.tailored)) {
          this.startWatching();
        } else {
          // Re-run of an already-tailored CV: nothing left to wait for.
          this.pending = false;
          this.expectedVariants = null;
        }
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
            next: (items) => this.setTailored(items),
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
