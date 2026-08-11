import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { Source, SourceInput, SourcesService } from '../../services/sources.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';

@Component({
  selector: 'app-sources',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent],
  templateUrl: './sources.component.html',
  styleUrl: './sources.component.scss',
})
export class SourcesComponent implements OnInit {
  sources: Source[] = [];
  loading = false;
  error: string | null = null;

  showForm = false;
  editingId: string | null = null;
  sourceForm;

  constructor(
    private fb: FormBuilder,
    private service: SourcesService,
    private confirm: ConfirmService,
    private toast: ToastService
  ) {
    this.sourceForm = this.fb.group({
      name: ['', Validators.required],
      url: ['', [Validators.required, Validators.pattern(/^https?:\/\/.+/)]],
      type: ['career_page', Validators.required],
    });
  }

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.list().subscribe({
      next: (sources) => {
        this.sources = sources;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load sources';
        this.loading = false;
      },
    });
  }

  openCreate(): void {
    this.editingId = null;
    this.sourceForm.reset({ name: '', url: '', type: 'career_page' });
    this.showForm = true;
  }

  openEdit(source: Source): void {
    this.editingId = source.id;
    this.sourceForm.setValue({ name: source.name, url: source.url, type: source.type });
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  save(): void {
    if (this.sourceForm.invalid) {
      return;
    }
    const raw = this.sourceForm.value as { name: string; url: string; type: string };
    const payload: SourceInput = { name: raw.name, url: raw.url, type: raw.type };
    const request = this.editingId
      ? this.service.update(this.editingId, payload)
      : this.service.create(payload);

    request.subscribe({
      next: () => {
        const wasEditing = !!this.editingId;
        this.showForm = false;
        this.editingId = null;
        this.toast.success(wasEditing ? 'Source updated.' : 'Source added.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to save source';
        this.toast.error('Failed to save source.');
      },
    });
  }

  async remove(source: Source): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: 'Delete source?',
      message: `Delete source "${source.name}"? Jobs already scraped from it will be kept.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Keep source',
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(source.id).subscribe({
      next: () => {
        this.toast.success('Source deleted.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to delete source';
        this.toast.error('Failed to delete source.');
      },
    });
  }
}
