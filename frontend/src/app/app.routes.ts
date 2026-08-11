import { Routes } from '@angular/router';

import { adminGuard } from './guards/admin.guard';
import { authGuard } from './guards/auth.guard';
import { LayoutComponent } from './components/layout/layout.component';
import { LoginComponent } from './components/login/login.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  {
    path: '',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'jobs', pathMatch: 'full' },
      {
        path: 'jobs',
        loadComponent: () =>
          import('./components/jobs/jobs.component').then((m) => m.JobsComponent),
      },
      {
        path: 'jobs/:id',
        loadComponent: () =>
          import('./components/job-detail/job-detail.component').then(
            (m) => m.JobDetailComponent
          ),
      },
      {
        path: 'sources',
        loadComponent: () =>
          import('./components/sources/sources.component').then((m) => m.SourcesComponent),
      },
      {
        path: 'cv',
        loadComponent: () =>
          import('./components/cv-editor/cv-editor.component').then(
            (m) => m.CvEditorComponent
          ),
      },
      {
        path: 'applications',
        loadComponent: () =>
          import('./components/applications/applications.component').then(
            (m) => m.ApplicationsComponent
          ),
      },
      {
        path: 'alerts',
        loadComponent: () =>
          import('./components/alerts/alerts.component').then((m) => m.AlertsComponent),
      },
      {
        path: 'notifications',
        loadComponent: () =>
          import('./components/notifications/notifications.component').then(
            (m) => m.NotificationsComponent
          ),
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./components/admin/admin.component').then((m) => m.AdminComponent),
      },
    ],
  },
  { path: '**', redirectTo: 'jobs' },
];


