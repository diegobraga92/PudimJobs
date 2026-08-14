import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { ThemeService } from './services/theme.service';
import { I18nService } from './services/i18n.service';
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
  constructor(readonly theme: ThemeService, readonly i18n: I18nService) {
    // Instantiating the theme + i18n services here applies the persisted/system
    // theme and language to <html> before the first paint of any route.
  }
}

