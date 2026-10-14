import { TestBed, ComponentFixture } from '@angular/core/testing';

import { AtsReport } from '../../services/cv.service';
import { I18nService } from '../../services/i18n.service';
import { AtsReportComponent } from './ats-report.component';

const REPORT: AtsReport = {
  score: 82,
  method: 'heuristic',
  factors: [
    { key: 'skills', label: 'Skill coverage', score: 0.8, weight: 0.4, detail: '4/5 skills.' },
  ],
  matched_skills: ['python', 'fastapi'],
  missing_skills: ['terraform'],
  recommendations: ['add or emphasise these required skills: terraform.'],
  warnings: ['Could not detect an email address.'],
  llm_summary: null,
};

describe('AtsReportComponent', () => {
  let fixture: ComponentFixture<AtsReportComponent>;
  let component: AtsReportComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AtsReportComponent] }).compileComponents();

    TestBed.inject(I18nService).setLanguage('en');
    fixture = TestBed.createComponent(AtsReportComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('report', REPORT);
    fixture.detectChanges();
  });

  it('renders the score, factors and skill chips', () => {
    const element = fixture.nativeElement as HTMLElement;
    const text = element.textContent ?? '';

    expect(text).toContain('82');
    expect(text).toContain('Skill coverage');
    expect(text).toContain('terraform');
    expect(text).toContain('4/5 skills.');
    expect(element.querySelector('.badge.badge-success')).toBeTruthy();
    expect(element.querySelector('.ats-bar span')).toBeTruthy();
  });

  it('bands the score colour and maps the method label', () => {
    expect(component.atsScoreClass(90)).toBe('badge-success');
    expect(component.atsScoreClass(60)).toBe('badge-warning');
    expect(component.atsScoreClass(10)).toBe('badge-danger');
    expect(component.atsMethodLabel('hybrid')).toBe(component.i18n.t('cv.ats.methodHybrid'));
    expect(component.atsMethodLabel('heuristic')).toBe(
      component.i18n.t('cv.ats.methodHeuristic')
    );
  });

  it('scales a 0..1 factor score into a bar width', () => {
    expect(component.factorPercent(0.8)).toBe(80);
    expect(component.factorPercent(0)).toBe(0);
    expect(component.factorPercent(2)).toBe(100);
  });

  it('labels the deterministic headline and shows the AI estimate beside it', () => {
    fixture.componentRef.setInput('report', {
      ...REPORT,
      deterministic_score: 70,
      llm_score: 30,
      method: 'hybrid',
    });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('70');
    expect(text).toContain(component.i18n.t('cv.ats.deterministic'));
    expect(text).toContain(component.i18n.t('cv.ats.llm', { score: 30 }));
    // The AI's own number never replaces the deterministic headline.
    expect(component.deterministicScore).toBe(70);
  });

  it('falls back to `score` for a report cached before deterministic_score existed', () => {
    expect(component.deterministicScore).toBe(REPORT.score);
  });
});
