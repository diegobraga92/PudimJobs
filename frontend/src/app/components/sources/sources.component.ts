import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import {
  AggregatorAdapter,
  AuthTestResult,
  DiscoveryProvider,
  ManualMetadata,
  Source,
  SourceAuth,
  SourceAuthInput,
  SourceInput,
  SourcePreview,
  SourcesService,
  isJobSource,
} from '../../services/sources.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppModalComponent } from '../../shared/modal/modal.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

/** i18n keys for the source-type dropdown and the list's Type column. */
const SOURCE_TYPE_KEYS: Record<string, string> = {
  career_page: 'sources.type.careerPage',
  aggregator: 'sources.type.aggregator',
  rss: 'sources.type.rss',
  discovery: 'sources.type.discovery',
  manual: 'sources.type.manual',
};

/** Columns of the sources table that can be sorted by clicking their header. */
export type SourceSortKey = 'name' | 'type' | 'jobs' | 'health' | 'last_scraped';

export type SortDirection = 'asc' | 'desc';

/** Header cells rendered above the list; the Actions column is not sortable. */
const SORTABLE_COLUMNS: ReadonlyArray<{ key: SourceSortKey; labelKey: string }> = [
  { key: 'name', labelKey: 'common.name' },
  { key: 'type', labelKey: 'common.type' },
  { key: 'jobs', labelKey: 'common.jobs' },
  { key: 'health', labelKey: 'common.health' },
  { key: 'last_scraped', labelKey: 'sources.lastScraped' },
];

/**
 * Severity ranks for the Health column: ascending means "best first", which is
 * more useful than the alphabetical degraded → failing → healthy.
 */
const HEALTH_RANK: Record<string, number> = { healthy: 0, degraded: 1, failing: 2 };

/**
 * Single-select quick filter for the source list. `''` means "All": every
 * source is shown (avoided ones still sink to the bottom — ADR 019).
 * `'automated'` keeps the scraped boards — the ones that can own jobs — and is
 * the mirror image of `'manual'`.
 */
export type SourceQuickFilter = '' | 'manual' | 'automated' | 'unhealthy' | 'due' | 'avoided';

@Component({
  selector: 'app-sources',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, AppIconComponent, AppModalComponent],
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

  /** Aggregator adapter + JSON config (shown when type === 'aggregator'). */
  adapter = 'generic_html_list';
  adapters: AggregatorAdapter[] = [];
  adaptersLoading = false;
  configJson = '';

  /** Discovery provider + config (shown when type === 'discovery'). */
  providers: DiscoveryProvider[] = [];
  providersLoading = false;
  discoveryProvider = '';

  /** Manual watchlist contract (cadence bounds + accepted keys), from the API. */
  manualMetadata: ManualMetadata | null = null;
  /** Manual watchlist re-check cadence (shown when type === 'manual'). */
  cadenceDays = 7;
  /** Free-form note kept with a manual source. */
  notes = '';
  /** Avoid-flag form state (edit form only) — never fetched, never reminded (ADR 019). */
  avoidSource = false;
  /** Optional "why" the user avoids the source, shown as a reminder in the list. */
  avoidReason = '';
  /**
   * `config` of the source being edited. Manual configs are *merged* with the
   * form values on save: `next_check_at`/`reminded_at` are engine-managed and
   * `PUT` replaces `config` wholesale, so rebuilding it from scratch would drop
   * them (and make the sweep re-remind an already-checked source).
   */
  private editingConfig: Record<string, unknown> = {};
  /** Id of the manual source currently being marked as checked. */
  checkingId: string | null = null;

  /** Id of the source whose avoid flag is currently being toggled. */
  avoidingId: string | null = null;
  /** When on, avoided sources are dropped from the table (they stay in the API). */
  hideAvoided = false;
  /** Quick filter applied to the list (single-select chip row). `''` = All. */
  sourceFilter: SourceQuickFilter = '';

  /** Sort applied by clicking a column header; `null` keeps the API order. */
  sortKey: SourceSortKey | null = null;
  sortDirection: SortDirection = 'asc';
  /** Header cells rendered by the template; the Actions column is not sortable. */
  readonly sortableColumns = SORTABLE_COLUMNS;

  /** Dry-run of the current form values (nothing is saved). */
  previewing = false;
  previewResult: SourcePreview | null = null;

  /** Per-source authentication panel state. */
  authSource: Source | null = null;
  authCurrent: SourceAuth | null = null;
  authType: SourceAuthInput['auth_type'] = 'none';
  authToken = '';
  authApiKey = '';
  authTestResult: AuthTestResult | null = null;
  authSaving = false;
  authTesting = false;

  constructor(
    private fb: FormBuilder,
    private service: SourcesService,
    private router: Router,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.sourceForm = this.fb.group({
      name: ['', Validators.required],
      url: ['', [Validators.required, Validators.pattern(/^https?:\/\/.+/)]],
      type: ['career_page', Validators.required],
      rate_limit_seconds: [
        30,
        [Validators.required, Validators.min(0), Validators.max(86400)],
      ],
      respect_robots_txt: [true],
    });
  }

  ngOnInit(): void {
    this.refresh();
    this.loadProviders();
    this.loadAdapters();
    this.loadManualMetadata();
  }

  /** Cadence bounds are published by the API, so they live in exactly one place. */
  private loadManualMetadata(): void {
    this.service.manualMetadata().subscribe({
      next: (metadata) => {
        this.manualMetadata = metadata;
        this.cadenceDays = metadata.cadence_days.default;
      },
      // The form still works offline: the input falls back to 1–365 below.
      error: () => {
        this.manualMetadata = null;
      },
    });
  }

  private loadProviders(): void {
    this.providersLoading = true;
    this.service.listProviders().subscribe({
      next: (providers) => {
        this.providers = providers;
        this.providersLoading = false;
      },
      error: () => {
        this.providersLoading = false;
      },
    });
  }

  private loadAdapters(): void {
    this.adaptersLoading = true;
    this.service.listAdapters().subscribe({
      next: (adapters) => {
        this.adapters = adapters;
        this.adaptersLoading = false;
      },
      error: () => {
        this.adaptersLoading = false;
      },
    });
  }

  /** The provider currently selected in the form (for hints/warnings). */
  get selectedProvider(): DiscoveryProvider | undefined {
    return this.providers.find((provider) => provider.name === this.discoveryProvider);
  }

  /** Human label for a source type (used in the list's Type column). */
  typeLabel(type: string): string {
    const key = SOURCE_TYPE_KEYS[type];
    return key ? this.i18n.t(key) : type;
  }

  /**
   * "Due in N days" / "Overdue by N days" for a manual source, or `''` when it
   * has no schedule yet. Whole days, measured from `next_check_at`.
   */
  dueText(source: Source): string {
    if (source.type !== 'manual' || !source.next_check_at) {
      return '';
    }
    const due = new Date(source.next_check_at).getTime();
    if (Number.isNaN(due)) {
      return '';
    }
    const days = Math.ceil((due - Date.now()) / 86_400_000) + 0;
    if (days === 0) {
      return this.i18n.t('sources.dueToday');
    }
    if (days === 1) {
      return this.i18n.t('sources.dueInOneDay');
    }
    if (days > 1) {
      return this.i18n.t('sources.dueInDays', { days });
    }
    if (days === -1) {
      return this.i18n.t('sources.overdueByOneDay');
    }
    return this.i18n.t('sources.overdueByDays', { days: Math.abs(days) });
  }

  /** The adapter currently selected in the form. */
  get selectedAdapter(): AggregatorAdapter | undefined {
    return this.adapters.find((adapter) => adapter.name === this.adapter);
  }

  /** Config contract of whatever the form currently dispatches on. */
  private get selectedContract(): AggregatorAdapter | DiscoveryProvider | undefined {
    return this.selectedProvider ?? this.selectedAdapter;
  }

  /** Keys the selected provider/adapter must receive. */
  get requiredKeys(): string[] {
    return this.selectedContract?.required_config ?? [];
  }

  /** Alternation groups, e.g. `[["url", "url_tpl"]]` → "url or url_tpl". */
  get requiredAnyKeys(): string[][] {
    return this.selectedContract?.required_any ?? [];
  }

  /** Keys that are accepted but optional. */
  get optionalKeys(): string[] {
    return this.selectedContract?.optional_config ?? [];
  }

  /** True when the backend publishes a usable example for the current choice. */
  get hasExampleConfig(): boolean {
    const example = this.selectedContract?.example_config;
    return !!example && Object.keys(example).length > 0;
  }

  /** Cadence bounds for the manual input, from the API (sane fallback when it is unreachable). */
  get cadenceMin(): number {
    return this.manualMetadata?.cadence_days.min ?? 1;
  }

  get cadenceMax(): number {
    return this.manualMetadata?.cadence_days.max ?? 365;
  }

  /** Prefill the config textarea with the backend's example for this choice. */
  applyExampleConfig(): void {
    const example = this.selectedContract?.example_config;
    if (!example) {
      return;
    }
    const config: Record<string, unknown> = { ...example };
    if (this.sourceForm.get('type')?.value === 'discovery') {
      delete config['provider'];
    }
    if (this.sourceForm.get('type')?.value === 'aggregator') {
      delete config['adapter'];
    }
    this.configJson = JSON.stringify(config, null, 2);
    this.previewResult = null;
  }

  /** Dry-run the current form values. Nothing is persisted: the API fetches and parses once and returns a sample, so selectors can be tuned before saving. */
  preview(): void {
    if (this.previewing) {
      return;
    }
    const url = this.sourceForm.get('url')?.value as string;
    const type = this.sourceForm.get('type')?.value as string;
    if (!url || this.sourceForm.get('url')?.invalid) {
      this.error = this.i18n.t('errors.invalidSourceUrl');
      this.toast.error(this.i18n.t('errors.invalidSourceUrl'));
      return;
    }
    if (type === 'discovery' && !this.discoveryProvider) {
      this.error = this.i18n.t('errors.chooseProvider');
      this.toast.error(this.i18n.t('errors.chooseProvider'));
      return;
    }
    const built = this.buildConfig(type);
    if (!built) {
      return;
    }
    this.previewing = true;
    this.previewResult = null;
    this.service.preview({ url, type, config: built }).subscribe({
      next: (result) => {
        this.previewing = false;
        this.previewResult = result;
      },
      error: () => {
        this.previewing = false;
        this.error = this.i18n.t('errors.failedPreviewSource');
        this.toast.error(this.i18n.t('errors.failedPreviewSource'));
      },
    });
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
        this.error = this.i18n.t('errors.failedLoadSources');
        this.loading = false;
      },
    });
  }

  /**
   * The rows to render. The quick filter narrows first, then "Hide avoided"
   * drops them; avoided sources that survive are listed *last* — they are a
   * reminder of what to stay away from, not work to do. The API keeps returning
   * them either way (ADR 019).
   */
  get visibleSources(): Source[] {
    const rows = this.sources
      .filter((source) => this.matchesFilter(source))
      .filter((source) => (this.hideAvoided ? !source.avoided : true));
    return rows.sort((a, b) => this.compareSources(a, b));
  }

  /** Clicking a new column sorts it ascending; the active one toggles direction. */
  sortBy(key: SourceSortKey): void {
    if (this.sortKey === key) {
      this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
      return;
    }
    this.sortKey = key;
    this.sortDirection = 'asc';
  }

  /** `aria-sort` of a header: only the active column advertises a direction. */
  ariaSort(key: SourceSortKey): 'ascending' | 'descending' | null {
    if (this.sortKey !== key) {
      return null;
    }
    return this.sortDirection === 'asc' ? 'ascending' : 'descending';
  }

  /**
   * Avoided sources always sink to the bottom (ADR 019) — they are a reminder,
   * not work — while the chosen sort orders the rows inside each group.
   */
  private compareSources(a: Source, b: Source): number {
    const avoided = Number(!!a.avoided) - Number(!!b.avoided);
    if (avoided !== 0) {
      return avoided;
    }
    const key = this.sortKey;
    if (!key) {
      return 0;
    }
    const direction = this.sortDirection === 'asc' ? 1 : -1;
    switch (key) {
      case 'name':
        return direction * this.compareText(a.name, b.name);
      case 'type':
        return direction * this.compareText(this.typeLabel(a.type), this.typeLabel(b.type));
      case 'jobs':
        return direction * ((a.jobs_count ?? 0) - (b.jobs_count ?? 0));
      case 'health':
        return direction * (this.healthRank(a.health) - this.healthRank(b.health));
      case 'last_scraped': {
        const aTime = this.scrapedTime(a);
        const bTime = this.scrapedTime(b);
        // Never-scraped boards stay last in both directions.
        if (aTime === null || bTime === null) {
          if (aTime === null && bTime === null) {
            return 0;
          }
          return aTime === null ? 1 : -1;
        }
        return direction * (aTime - bTime);
      }
    }
  }

  /** Case/accent-insensitive text order in the active language. */
  private compareText(a: string, b: string): number {
    return a.localeCompare(b, this.i18n.current, { sensitivity: 'base' });
  }

  private healthRank(health: string): number {
    return HEALTH_RANK[health] ?? Number.MAX_SAFE_INTEGER;
  }

  /** Epoch millis of `last_scraped`, or `null` when missing/unparseable. */
  private scrapedTime(source: Source): number | null {
    if (!source.last_scraped) {
      return null;
    }
    const time = new Date(source.last_scraped).getTime();
    return Number.isNaN(time) ? null : time;
  }

  /** Predicate of the active quick filter (`''` keeps every source). */
  private matchesFilter(source: Source): boolean {
    switch (this.sourceFilter) {
      case 'manual':
        return source.type === 'manual';
      case 'automated':
        return source.type !== 'manual';
      case 'unhealthy':
        return source.health !== 'healthy';
      case 'due':
        return source.type === 'manual' && !!source.due;
      case 'avoided':
        return !!source.avoided;
      default:
        return true;
    }
  }

  /** Selects a quick filter (single-select); `''` shows every source again. */
  setSourceFilter(filter: SourceQuickFilter): void {
    this.sourceFilter = filter;
  }

  /**
   * True when the row has jobs worth opening: the scraped boards, plus any
   * source that already owns a job (a watchlist cannot be fetched, but a job
   * can still be attached to it by hand).
   */
  canViewJobs(source: Source): boolean {
    return isJobSource(source);
  }

  /**
   * Open the jobs list narrowed to this board. The Jobs page reads the query
   * param once and seeds its Source filter, so there is a single list of jobs
   * to maintain (search, pagination and cleanup all keep working there).
   */
  viewJobs(source: Source): void {
    this.router.navigate(['/jobs'], { queryParams: { source_id: source.id } });
  }

  /** Live counts shown inside the filter chips (0 hides the counter). */
  get manualCount(): number {
    return this.sources.filter((source) => source.type === 'manual').length;
  }

  get automatedCount(): number {
    return this.sources.filter((source) => source.type !== 'manual').length;
  }

  get unhealthyCount(): number {
    return this.sources.filter((source) => source.health !== 'healthy').length;
  }

  get dueCount(): number {
    return this.sources.filter((source) => source.type === 'manual' && !!source.due).length;
  }

  /** How many sources are flagged as avoided (0 hides the toggle's counter). */
  get avoidedCount(): number {
    return this.sources.filter((source) => source.avoided).length;
  }

  toggleHideAvoided(): void {
    this.hideAvoided = !this.hideAvoided;
  }

  /**
   * Flags a source as avoided (never fetched, never reminded about) or restores
   * it. One click, no reason: "why" is edited in the form where there is room
   * for it — and the API keeps an existing reason when none is sent.
   */
  toggleAvoided(source: Source): void {
    if (this.avoidingId) {
      return;
    }
    this.avoidingId = source.id;
    const avoided = !source.avoided;
    this.service.setSourceAvoided(source.id, avoided).subscribe({
      next: (updated) => {
        this.avoidingId = null;
        this.sources = this.sources.map((item) => (item.id === updated.id ? updated : item));
        this.toast.success(
          this.i18n.t(avoided ? 'sources.sourceAvoided' : 'sources.sourceRestored')
        );
      },
      error: () => {
        this.avoidingId = null;
        this.error = this.i18n.t('errors.failedAvoidSource');
        this.toast.error(this.i18n.t('errors.failedAvoidSource'));
      },
    });
  }

  openCreate(): void {
    this.editingId = null;
    this.sourceForm.reset({
      name: '',
      url: '',
      type: 'career_page',
      rate_limit_seconds: 30,
      respect_robots_txt: true,
    });
    this.adapter = 'generic_html_list';
    this.configJson = '';
    this.discoveryProvider = '';
    this.cadenceDays = this.manualMetadata?.cadence_days.default ?? 7;
    this.notes = '';
    // A brand-new source cannot be avoided yet: `POST /sources` has no such field.
    this.avoidSource = false;
    this.avoidReason = '';
    this.editingConfig = {};
    this.previewResult = null;
    this.showForm = true;
  }

  openEdit(source: Source): void {
    this.editingId = source.id;
    this.sourceForm.setValue({
      name: source.name,
      url: source.url,
      type: source.type,
      rate_limit_seconds: source.rate_limit_seconds ?? 30,
      respect_robots_txt: source.respect_robots_txt ?? true,
    });
    this.adapter = (source.config?.['adapter'] as string) ?? 'generic_html_list';
    this.discoveryProvider = (source.config?.['provider'] as string) ?? '';
    this.cadenceDays = Number(
      source.config?.['cadence_days'] ?? this.manualMetadata?.cadence_days.default ?? 7
    );
    // Kept so a manual save can merge instead of replacing the whole config.
    this.editingConfig = { ...(source.config ?? {}) };
    this.notes = String(source.config?.['notes'] ?? '');
    this.avoidSource = source.avoided ?? false;
    this.avoidReason = source.avoid_reason ?? '';
    if (source.type === 'discovery') {
      const rest = { ...(source.config ?? {}) };
      delete rest['provider'];
      this.configJson = Object.keys(rest).length ? JSON.stringify(rest, null, 2) : '';
    } else {
      this.configJson = source.config ? JSON.stringify(source.config, null, 2) : '';
    }
    this.previewResult = null;
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
    this.editingConfig = {};
    this.notes = '';
    this.avoidSource = false;
    this.avoidReason = '';
    this.previewResult = null;
  }

  /** The `config` to send for the current form state, or null when the JSON is invalid (an error toast is shown). */
  private buildConfig(type: string): Record<string, unknown> | null {
    if (type === 'manual') {
      // Merge with what the source already carries: `next_check_at` and
      // `reminded_at` are engine-managed and PUT replaces config wholesale, so
      // dropping them would make the sweep re-remind a fresh source.
      const config: Record<string, unknown> = {
        ...this.editingConfig,
        cadence_days: this.cadenceDays,
      };
      const notes = this.notes.trim();
      if (notes) {
        config['notes'] = notes;
      } else {
        // Clearing the field removes the note rather than storing an empty one.
        delete config['notes'];
      }
      return config;
    }
    const parsed = this.parseConfigJson(type);
    if (parsed === null) {
      return null;
    }
    if (type === 'aggregator') {
      return { ...parsed, adapter: this.adapter };
    }
    if (type === 'discovery') {
      return { ...parsed, provider: this.discoveryProvider };
    }
    return parsed;
  }

  private parseConfigJson(type: string): Record<string, unknown> | null {
    const raw = this.configJson.trim();
    if (!raw) {
      return {};
    }
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('config must be a JSON object');
      }
      return parsed as Record<string, unknown>;
    } catch {
      const key =
        type === 'discovery'
          ? 'errors.invalidDiscoveryJson'
          : 'errors.invalidAggregatorJson';
      this.error = this.i18n.t(key);
      this.toast.error(this.i18n.t(key));
      return null;
    }
  }

  save(): void {
    if (this.sourceForm.invalid) {
      return;
    }
    const raw = this.sourceForm.value as {
      name: string;
      url: string;
      type: string;
      rate_limit_seconds: number;
      respect_robots_txt: boolean;
    };
    const payload: SourceInput = {
      name: raw.name,
      url: raw.url,
      type: raw.type,
      rate_limit_seconds: raw.rate_limit_seconds,
      respect_robots_txt: raw.respect_robots_txt,
    };
    if (raw.type === 'discovery' && !this.discoveryProvider) {
      this.error = this.i18n.t('errors.chooseProvider');
      this.toast.error(this.i18n.t('errors.chooseProvider'));
      return;
    }
    if (raw.type === 'aggregator' || raw.type === 'discovery' || raw.type === 'manual') {
      const config = this.buildConfig(raw.type);
      if (!config) {
        return;
      }
      payload.config = config;
    }
    if (this.editingId) {
      // The avoid flag is a statement, not a partial patch: sending the form's
      // value is what restores a source the user un-checks. Only edits can flip
      // it — a brand-new source has nothing to avoid yet.
      payload.avoided = this.avoidSource;
      payload.avoid_reason = this.avoidReason.trim();
    }
    const request = this.editingId
      ? this.service.update(this.editingId, payload)
      : this.service.create(payload);

    request.subscribe({
      next: () => {
        const wasEditing = !!this.editingId;
        this.showForm = false;
        this.editingId = null;
        this.toast.success(wasEditing ? this.i18n.t('sources.sourceUpdated') : this.i18n.t('sources.sourceAdded'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedSaveSource');
        this.toast.error(this.i18n.t('errors.failedSaveSource'));
      },
    });
  }

  async remove(source: Source): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('sources.deleteTitle'),
      message: this.i18n.t('sources.deleteMessage', { name: source.name }),
      confirmLabel: this.i18n.t('common.delete'),
      cancelLabel: this.i18n.t('sources.keepSource'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(source.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('sources.sourceDeleted'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteSource');
        this.toast.error(this.i18n.t('errors.failedDeleteSource'));
      },
    });
  }

  /** Marks a manual watchlist source as checked by hand and schedules the next reminder. */
  markChecked(source: Source): void {
    if (this.checkingId) {
      return;
    }
    this.checkingId = source.id;
    this.service.checkSource(source.id).subscribe({
      next: (updated) => {
        this.checkingId = null;
        this.sources = this.sources.map((item) => (item.id === updated.id ? updated : item));
        this.toast.success(this.i18n.t('sources.checked'));
      },
      error: () => {
        this.checkingId = null;
        this.error = this.i18n.t('errors.failedCheckSource');
        this.toast.error(this.i18n.t('errors.failedCheckSource'));
      },
    });
  }

  /** Opens the authentication panel for a source (login-required boards). */
  openAuth(source: Source): void {
    this.authSource = source;
    this.authType = 'none';
    this.authToken = '';
    this.authApiKey = '';
    this.authTestResult = null;
    this.authSaving = false;
    this.authTesting = false;
    this.service.getAuth(source.id).subscribe({
      next: (auth) => {
        this.authCurrent = auth;
        this.authType = auth.auth_type;
      },
      error: () => {
        this.authCurrent = { auth_type: 'none', has_auth: false, updated_at: null };
      },
    });
  }

  closeAuth(): void {
    this.authSource = null;
    this.authCurrent = null;
    this.authTestResult = null;
  }

  saveAuth(): void {
    if (!this.authSource || this.authSaving) {
      return;
    }
    const payload: SourceAuthInput = { auth_type: this.authType };
    if (this.authType === 'token') {
      payload.token = this.authToken;
    }
    if (this.authType === 'api_key') {
      payload.api_key = this.authApiKey;
    }
    this.authSaving = true;
    this.service.updateAuth(this.authSource.id, payload).subscribe({
      next: (auth) => {
        this.authSaving = false;
        this.authCurrent = auth;
        this.authType = auth.auth_type;
        this.authToken = '';
        this.authApiKey = '';
        this.authTestResult = null;
        this.toast.success(this.i18n.t('sources.authSaved'));
      },
      error: () => {
        this.authSaving = false;
        this.error = this.i18n.t('errors.failedSaveAuth');
        this.toast.error(this.i18n.t('errors.failedSaveAuth'));
      },
    });
  }

  testAuth(): void {
    if (!this.authSource || this.authTesting) {
      return;
    }
    this.authTesting = true;
    this.authTestResult = null;
    this.service.testAuth(this.authSource.id).subscribe({
      next: (result) => {
        this.authTesting = false;
        this.authTestResult = result;
        if (result.ok) {
          this.toast.success(this.i18n.t('sources.authOk'));
        } else {
          this.toast.error(result.error ? this.i18n.t('sources.authFailedWith', { error: result.error }) : this.i18n.t('sources.authFailed'));
        }
      },
      error: () => {
        this.authTesting = false;
        this.error = this.i18n.t('errors.failedRunAuthTest');
        this.toast.error(this.i18n.t('errors.failedRunAuthTest'));
      },
    });
  }

  clearAuth(): void {
    if (!this.authSource) {
      return;
    }
    this.service.deleteAuth(this.authSource.id).subscribe({
      next: () => {
        this.authCurrent = { auth_type: 'none', has_auth: false, updated_at: null };
        this.authType = 'none';
        this.authToken = '';
        this.authApiKey = '';
        this.authTestResult = null;
        this.toast.success(this.i18n.t('sources.authCleared'));
      },
      error: () => {
        this.error = this.i18n.t('errors.failedClearAuth');
        this.toast.error(this.i18n.t('errors.failedClearAuth'));
      },
    });
  }
}
