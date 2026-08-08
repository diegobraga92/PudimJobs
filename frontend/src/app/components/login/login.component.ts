import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  loginForm;
  error: string | null = null;
  loading = false;

  constructor(
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });
  }

  submit(): void {
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
        this.error = 'Invalid email or password';
      },
    });
  }
}
