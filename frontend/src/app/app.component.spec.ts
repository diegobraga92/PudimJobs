import { TestBed, ComponentFixture } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { AppComponent } from './app.component';
import { HealthCheckService, HealthResponse } from './health-check.service';

describe('AppComponent', () => {
  let fixture: ComponentFixture<AppComponent>;
  let healthServiceSpy: jasmine.SpyObj<HealthCheckService>;

  const healthyResponse: HealthResponse = {
    status: 'ok',
    timestamp: '2026-01-06T08:00:00+00:00',
    db: 'connected',
  };

  beforeEach(async () => {
    healthServiceSpy = jasmine.createSpyObj('HealthCheckService', ['check']);
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [{ provide: HealthCheckService, useValue: healthServiceSpy }],
    }).compileComponents();
  });

  it('should create the app', () => {
    fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the app title', () => {
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('PudimJobs');
  });

  it('should display healthy status when the backend responds', () => {
    healthServiceSpy.check.and.returnValue(of(healthyResponse));
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const details = compiled.querySelector('.status.healthy');
    expect(details).toBeTruthy();
    expect(details?.textContent).toContain('ok');
    expect(details?.textContent).toContain('connected');
  });

  it('should display an error message when the backend is unreachable', () => {
    healthServiceSpy.check.and.returnValue(
      throwError(() => new Error('connection refused'))
    );
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const degraded = compiled.querySelector('.status.degraded');
    expect(degraded).toBeTruthy();
    expect(degraded?.textContent).toContain('Failed to connect to backend');
  });
});
