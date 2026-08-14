import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';
import { I18nService } from '../../services/i18n.service';
import { AppIconComponent } from '../../shared/icons/icon.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  loginForm;
  error: string | null = null;
  loading = false;
  submitted = false;
  showPassword = false;

  constructor(
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router,
    readonly i18n: I18nService
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });
  }

  submit(): void {
    this.submitted = true;
    if (this.loginForm.invalid || this.loading) {
      return;
    }
    this.loading = true;
    this.error = null;

    const { email, password } = this.loginForm.value as {
      email: string;
      password: string;
    };
    this.auth.login(email, password).subscribe({
      next: (response) => {
        this.auth.storeToken(response.access_token);
        this.router.navigate(['/jobs']);
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('login.invalidCredentials');
      },
    });
  }
}

