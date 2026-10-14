import { Component, Input, inject } from '@angular/core';

import { AtsReport } from '../../services/cv.service';
import { I18nService } from '../../services/i18n.service';

/** Read-only rendering of an ATS score report (see ADR 013): the score dial, weighted factors, matched/missing skills, recommendations and parser warnings. */
@Component({
  selector: 'app-ats-report',
  standalone: true,
  templateUrl: './ats-report.component.html',
  styleUrl: './ats-report.component.scss',
})
export class AtsReportComponent {
  readonly i18n = inject(I18nService);

  @Input({ required: true }) report!: AtsReport;

  /** The headline number: the deterministic baseline. Falls back to `score` for a report cached before `deterministic_score` existed (ADR 013 amendment). */
  get deterministicScore(): number {
    return this.report.deterministic_score ?? this.report.score;
  }

  /** 0..100 score rendered as a bar width. */
  factorPercent(score: number): number {
    return Math.max(0, Math.min(100, Math.round(score * 100)));
  }

  /** Badge colour for an ATS score (green ≥ 75, amber ≥ 50, red below). */
  atsScoreClass(score: number): string {
    if (score >= 75) {
      return 'badge-success';
    }
    return score >= 50 ? 'badge-warning' : 'badge-danger';
  }

  atsMethodLabel(method: string): string {
    return method === 'hybrid'
      ? this.i18n.t('cv.ats.methodHybrid')
      : this.i18n.t('cv.ats.methodHeuristic');
  }
}
