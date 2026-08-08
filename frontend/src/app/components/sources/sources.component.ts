import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { Source, SourceInput, SourcesService } from '../../services/sources.service';

@Component({
  selector: 'app-sources',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
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

  constructor(private fb: FormBuilder, private service: SourcesService) {
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
        this.showForm = false;
        this.editingId = null;
        this.refresh();
      },
      error: () => (this.error = 'Failed to save source'),
    });
  }

  remove(source: Source): void {
    if (!window.confirm(`Delete source "${source.name}"?`)) {
      return;
    }
    this.service.delete(source.id).subscribe({
      next: () => this.refresh(),
      error: () => (this.error = 'Failed to delete source'),
    });
  }
}
