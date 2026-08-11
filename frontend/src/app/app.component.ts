import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { ThemeService } from './services/theme.service';
import { ConfirmDialogComponent } from './shared/confirm/confirm-dialog.component';
import { ToastViewportComponent } from './shared/toast/toast-viewport.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, ToastViewportComponent, ConfirmDialogComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  constructor(readonly theme: ThemeService) {
    // Instantiating the theme service here applies the persisted/system theme
    // to <html> before the first paint of any route (login included).
  }
}

