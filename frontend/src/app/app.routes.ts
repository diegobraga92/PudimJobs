import { Routes } from '@angular/router';

import { authGuard } from './guards/auth.guard';
import { ApplicationsComponent } from './components/applications/applications.component';
import { CvEditorComponent } from './components/cv-editor/cv-editor.component';
import { JobDetailComponent } from './components/job-detail/job-detail.component';
import { JobsComponent } from './components/jobs/jobs.component';
import { LayoutComponent } from './components/layout/layout.component';
import { LoginComponent } from './components/login/login.component';
import { SourcesComponent } from './components/sources/sources.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  {
    path: '',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'jobs', pathMatch: 'full' },
      { path: 'jobs', component: JobsComponent },
      { path: 'jobs/:id', component: JobDetailComponent },
      { path: 'sources', component: SourcesComponent },
      { path: 'cv', component: CvEditorComponent },
      { path: 'applications', component: ApplicationsComponent },
    ],
  },
  { path: '**', redirectTo: 'jobs' },
];

