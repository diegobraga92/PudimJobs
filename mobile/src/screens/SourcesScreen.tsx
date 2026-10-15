import { useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { FormField } from '@/components/ui/FormField';
import { Icon } from '@/components/icons/Icon';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { TextArea } from '@/components/ui/TextArea';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import {
  useCheckSource,
  useClearSourceAuth,
  useDeleteSource,
  useManualMetadata,
  useProviders,
  useSaveSource,
  useSaveSourceAuth,
  useSetSourceAvoided,
  useSourceAuth,
  useSources,
  useTestSourceAuth,
} from '@/hooks/useSources';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { Source, SourceInput } from '@/types';
import { dateLocale, daysUntil, shortDate } from '@/utils/dates';

const SOURCE_TYPES = ['career_page', 'aggregator', 'rss', 'discovery', 'manual'] as const;

/** i18n keys for the source-type dropdown (the values are snake_case). */
const SOURCE_TYPE_KEYS: Record<string, string> = {
  career_page: 'sources.type.careerPage',
  aggregator: 'sources.type.aggregator',
  rss: 'sources.type.rss',
  discovery: 'sources.type.discovery',
  manual: 'sources.type.manual',
};

interface SourceFormState {
  name: string;
  url: string;
  type: string;
  rate_limit_seconds: string;
  respect_robots_txt: boolean;
  cadence_days: string;
  notes: string;
  /** Avoid flag (edits only): never scraped, never reminded — see ADR 019. */
  avoided: boolean;
  avoid_reason: string;
}

const EMPTY_FORM: SourceFormState = {
  name: '',
  url: '',
  type: 'career_page',
  rate_limit_seconds: '30',
  respect_robots_txt: true,
  cadence_days: '7',
  notes: '',
  avoided: false,
  avoid_reason: '',
};

/** Cadence bounds used until the API publishes them (see `manualMetadata`). */
const FALLBACK_CADENCE = { default: 7, min: 1, max: 365 };

/** Sources management — mirrors the web sources page (form, list, auth panel). */
export function SourcesScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: sources = [], isPending, error } = useSources();
  const { data: providers = [] } = useProviders();
  const { data: manualMetadata } = useManualMetadata();
  /** Cadence bounds come from the API so they are not duplicated here. */
  const cadenceBounds = manualMetadata?.cadence_days ?? FALLBACK_CADENCE;
  const saveSource = useSaveSource();
  const deleteSource = useDeleteSource();
  const checkSource = useCheckSource();
  const setSourceAvoided = useSetSourceAvoided();

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SourceFormState>(EMPTY_FORM);
  const [adapter, setAdapter] = useState('generic_html_list');
  const [configJson, setConfigJson] = useState('');
  const [discoveryProvider, setDiscoveryProvider] = useState('');
  const [authSource, setAuthSource] = useState<Source | null>(null);
  /**
   * `config` of the source being edited. Manual configs are merged with the form
   * values on save because `PUT` replaces `config` wholesale and
   * `next_check_at`/`reminded_at` are engine-managed — dropping them would make
   * the sweep re-remind an already-checked source.
   */
  const [editingConfig, setEditingConfig] = useState<Record<string, unknown>>({});

  const update = <K extends keyof SourceFormState>(key: K, value: SourceFormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM, cadence_days: String(cadenceBounds.default) });
    setAdapter('generic_html_list');
    setConfigJson('');
    setDiscoveryProvider('');
    setEditingConfig({});
    setShowForm(true);
  };

  const openEdit = (source: Source) => {
    setEditingId(source.id);
    setForm({
      name: source.name,
      url: source.url,
      type: source.type,
      rate_limit_seconds: String(source.rate_limit_seconds ?? 30),
      respect_robots_txt: source.respect_robots_txt ?? true,
      cadence_days: String(source.config?.['cadence_days'] ?? cadenceBounds.default),
      notes: String(source.config?.['notes'] ?? ''),
      avoided: source.avoided ?? false,
      avoid_reason: source.avoid_reason ?? '',
    });
    // Kept so a manual save can merge instead of replacing the whole config.
    setEditingConfig({ ...(source.config ?? {}) });
    setAdapter((source.config?.['adapter'] as string) ?? 'generic_html_list');
    setDiscoveryProvider((source.config?.['provider'] as string) ?? '');
    const rest = { ...(source.config ?? {}) };
    delete rest['adapter'];
    delete rest['provider'];
    setConfigJson(Object.keys(rest).length ? JSON.stringify(rest, null, 2) : '');
    setShowForm(true);
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditingId(null);
    setEditingConfig({});
  };

  const save = () => {
    if (!form.name.trim() || !form.url.trim()) {
      toast.error(i18n.t('errors.failedSaveSource'));
      return;
    }
    if (!/^https?:\/\/.+/.test(form.url.trim())) {
      toast.error(i18n.t('errors.failedSaveSource'));
      return;
    }
    const rate = Number(form.rate_limit_seconds);
    if (!Number.isFinite(rate) || rate < 0 || rate > 86400) {
      toast.error(i18n.t('errors.failedSaveSource'));
      return;
    }
    const cadence = Number(form.cadence_days);
    if (
      form.type === 'manual' &&
      (!Number.isFinite(cadence) || cadence < cadenceBounds.min || cadence > cadenceBounds.max)
    ) {
      toast.error(i18n.t('errors.failedSaveSource'));
      return;
    }
    const payload: SourceInput = {
      name: form.name,
      url: form.url,
      type: form.type,
      rate_limit_seconds: rate,
      respect_robots_txt: form.respect_robots_txt,
    };
    if (form.type === 'aggregator') {
      const config: Record<string, unknown> = { adapter };
      if (configJson.trim()) {
        try {
          Object.assign(config, JSON.parse(configJson.trim()));
        } catch {
          toast.error(i18n.t('errors.invalidAggregatorJson'));
          return;
        }
      }
      config['adapter'] = adapter;
      payload.config = config;
    }
    if (form.type === 'discovery') {
      if (!discoveryProvider) {
        toast.error(i18n.t('errors.chooseProvider'));
        return;
      }
      const config: Record<string, unknown> = { provider: discoveryProvider };
      if (configJson.trim()) {
        try {
          Object.assign(config, JSON.parse(configJson.trim()));
        } catch {
          toast.error(i18n.t('errors.invalidDiscoveryJson'));
          return;
        }
      }
      config['provider'] = discoveryProvider;
      payload.config = config;
    }
    if (form.type === 'manual') {
      // Merge with what the source already carries: `next_check_at` and
      // `reminded_at` are engine-managed and PUT replaces config wholesale, so
      // dropping them would make the sweep re-remind a fresh source.
      const config: Record<string, unknown> = { ...editingConfig, cadence_days: cadence };
      const notes = form.notes.trim();
      if (notes) {
        config.notes = notes;
      } else {
        // Clearing the field removes the note rather than storing an empty one.
        delete config.notes;
      }
      payload.config = config;
    }
    if (editingId) {
      // The avoid flag is a statement, not a patch: sending the form's value is
      // what restores an un-checked source. A brand-new source has nothing to
      // avoid yet, and `POST /sources` has no such fields.
      payload.avoided = form.avoided;
      payload.avoid_reason = form.avoid_reason.trim();
    }
    saveSource.mutate(
      { id: editingId ?? undefined, payload },
      {
        onSuccess: () => {
          const wasEditing = !!editingId;
          setShowForm(false);
          setEditingId(null);
          toast.success(
            wasEditing ? i18n.t('sources.sourceUpdated') : i18n.t('sources.sourceAdded'),
          );
        },
        onError: () => toast.error(i18n.t('errors.failedSaveSource')),
      },
    );
  };

  const remove = async (source: Source) => {
    const confirmed = await confirm.confirm({
      title: i18n.t('sources.deleteTitle'),
      message: i18n.t('sources.deleteMessage', { name: source.name }),
      confirmLabel: i18n.t('common.delete'),
      cancelLabel: i18n.t('sources.keepSource'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteSource.mutate(source.id, {
      onSuccess: () => toast.success(i18n.t('sources.sourceDeleted')),
      onError: () => toast.error(i18n.t('errors.failedDeleteSource')),
    });
  };

  /** Marks a manual watchlist source as checked by hand; schedules the next reminder. */
  const markChecked = (source: Source) => {
    checkSource.mutate(source.id, {
      onSuccess: () => toast.success(i18n.t('sources.checked')),
      onError: () => toast.error(i18n.t('errors.failedCheckSource')),
    });
  };

  /**
   * Flags a source as avoided (never scraped, never reminded about) or restores
   * it. One tap and no reason: "why" is edited in the form, and the API keeps an
   * existing reason when none is sent.
   */
  const toggleAvoided = (source: Source) => {
    const avoided = !source.avoided;
    setSourceAvoided.mutate(
      { id: source.id, avoided },
      {
        onSuccess: () =>
          toast.success(i18n.t(avoided ? 'sources.sourceAvoided' : 'sources.sourceRestored')),
        onError: () => toast.error(i18n.t('errors.failedAvoidSource')),
      },
    );
  };

  /**
   * Avoided sources are listed last: they are a reminder of what to stay away
   * from, not work to do. The API keeps returning them either way (ADR 019).
   */
  const sortedSources = [...sources].sort((a, b) => Number(!!a.avoided) - Number(!!b.avoided));

  /**
   * "Due in N days" / "Overdue by N days" for a manual source, or `''` when it
   * has no schedule yet. Whole days, measured from `next_check_at`.
   */
  const dueText = (source: Source): string => {
    const days = daysUntil(source.next_check_at);
    if (days === null) {
      return '';
    }
    if (days === 0) {
      return i18n.t('sources.dueToday');
    }
    if (days === 1) {
      return i18n.t('sources.dueInOneDay');
    }
    if (days > 1) {
      return i18n.t('sources.dueInDays', { days });
    }
    if (days === -1) {
      return i18n.t('sources.overdueByOneDay');
    }
    return i18n.t('sources.overdueByDays', { days: Math.abs(days) });
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.colors.bg }]}
      contentContainerStyle={styles.content}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: theme.colors.text }]}>{i18n.t('sources.title')}</Text>
        <Button size="sm" onPress={openCreate}>
          <Icon name="plus" size={16} />
          {i18n.t('sources.addSource')}
        </Button>
      </View>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadSources')}</Alert> : null}

      {showForm ? (
        <View
          style={[
            styles.panel,
            { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
          ]}
        >
          <Text style={[styles.formTitle, { color: theme.colors.text }]}>
            {editingId ? i18n.t('sources.editSource') : i18n.t('sources.addSource')}
          </Text>

          <FormField label={i18n.t('common.name')}>
            <Input
              value={form.name}
              onChangeText={(value) => update('name', value)}
              placeholder="Acme Careers"
            />
          </FormField>

          <FormField label={i18n.t('common.url')}>
            <Input
              value={form.url}
              onChangeText={(value) => update('url', value)}
              placeholder="https://acme.example/careers"
              autoCapitalize="none"
            />
          </FormField>

          <FormField label={i18n.t('common.type')}>
            <Select
              value={form.type}
              options={SOURCE_TYPES.map((type) => ({
                label: i18n.t(SOURCE_TYPE_KEYS[type] ?? type),
                value: type,
              }))}
              onValueChange={(value) => update('type', value)}
            />
          </FormField>

          {form.type === 'aggregator' ? (
            <>
              <FormField label={i18n.t('sources.adapter')}>
                <Select
                  value={adapter}
                  options={[
                    { label: i18n.t('sources.genericHtmlList'), value: 'generic_html_list' },
                  ]}
                  onValueChange={setAdapter}
                />
              </FormField>
              <FormField label={i18n.t('sources.adapterConfig')}>
                <TextArea
                  value={configJson}
                  onChangeText={setConfigJson}
                  minHeight={90}
                  placeholder='{ "item_selector": "li.job", "title_selector": "h2", "url_selector": "a", "next_page_selector": "a.next", "max_pages": 3 }'
                />
              </FormField>
              <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                {i18n.t('sources.adapterHintPrefix')} <Text style={styles.code}>max_pages</Text>
                {' '}
                {i18n.t('sources.adapterHintSuffix')} <Text style={styles.code}>next_page_tpl</Text>
                {' '}
                {i18n.t('sources.adapterHintTpl')} <Text style={styles.code}>url_tpl</Text>
                {' '}
                {i18n.t('sources.adapterHintUrlTpl')}
              </Text>
            </>
          ) : null}

          {form.type === 'discovery' ? (
            <FormField label={i18n.t('sources.provider')}>
              <Select
                value={discoveryProvider || null}
                options={providers.map((provider) => ({
                  label:
                    provider.name + (provider.requires_key ? ` · ${i18n.t('common.apiKey')}` : ''),
                  value: provider.name,
                }))}
                onValueChange={setDiscoveryProvider}
                placeholder={i18n.t('sources.chooseProviderOption')}
              />
            </FormField>
          ) : null}

          {form.type === 'discovery' || form.type === 'aggregator' ? (
            <FormField label={i18n.t('sources.adapterConfig')}>
              <TextArea value={configJson} onChangeText={setConfigJson} minHeight={80} />
            </FormField>
          ) : null}

          {form.type === 'manual' ? (
            <>
              <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                {i18n.t('sources.manualHint')}
              </Text>
              <FormField label={i18n.t('sources.cadence')}>
                <Input
                  value={form.cadence_days}
                  onChangeText={(value) => update('cadence_days', value)}
                  keyboardType="number-pad"
                />
              </FormField>
              <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                {i18n.t('sources.cadenceHint')}
              </Text>
              <FormField label={i18n.t('sources.notes')}>
                <TextArea
                  value={form.notes}
                  onChangeText={(value) => update('notes', value)}
                  minHeight={60}
                />
              </FormField>
              <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                {i18n.t('sources.notesHint')}
              </Text>
            </>
          ) : null}

          <View style={styles.row}>
            <FormField label={i18n.t('sources.rateLimit')} style={styles.rowField}>
              <Input
                value={form.rate_limit_seconds}
                onChangeText={(value) => update('rate_limit_seconds', value)}
                keyboardType="number-pad"
              />
            </FormField>
            <FormField label={i18n.t('sources.respectRobots')} style={styles.rowField}>
              <View style={styles.switchWrap}>
                <Switch
                  value={form.respect_robots_txt}
                  onValueChange={(value) => update('respect_robots_txt', value)}
                />
              </View>
            </FormField>
          </View>

          {/* Only an existing source can be avoided: `POST /sources` has no flag. */}
          {editingId ? (
            <>
              <FormField label={i18n.t('sources.avoidSource')}>
                <View style={styles.switchWrap}>
                  <Switch
                    value={form.avoided}
                    onValueChange={(value) => update('avoided', value)}
                  />
                </View>
              </FormField>
              <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                {i18n.t('sources.avoidSourceHint')}
              </Text>
              {form.avoided ? (
                <>
                  <FormField label={i18n.t('sources.avoidReason')}>
                    <Input
                      value={form.avoid_reason}
                      onChangeText={(value) => update('avoid_reason', value)}
                      maxLength={280}
                    />
                  </FormField>
                  <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
                    {i18n.t('sources.avoidReasonHint')}
                  </Text>
                </>
              ) : null}
            </>
          ) : null}

          <View style={styles.formActions}>
            <Button variant="ghost" onPress={cancelForm}>
              {i18n.t('common.cancel')}
            </Button>
            <Button
              onPress={save}
              loading={saveSource.isPending}
              disabled={!form.name.trim() || !form.url.trim()}
            >
              {editingId ? i18n.t('common.save') : i18n.t('sources.addSource')}
            </Button>
          </View>
        </View>
      ) : null}

      {!isPending && sources.length === 0 ? (
        <EmptyState
          icon="globe"
          title={i18n.t('sources.noSourcesYet')}
          hint={i18n.t('sources.noSourcesHint')}
          action={
            <Button onPress={openCreate}>
              <Icon name="plus" size={16} />
              {i18n.t('sources.addFirstSource')}
            </Button>
          }
        />
      ) : null}

      {sortedSources.map((source) => (
        <View
          key={source.id}
          style={[
            styles.sourceCard,
            { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
            // Dimmed, still readable on purpose: avoided is a reminder, not a deletion.
            source.avoided ? styles.avoidedCard : null,
          ]}
        >
          <View style={styles.sourceHead}>
            <Pressable
              onPress={() => void Linking.openURL(source.url)}
              accessibilityRole="link"
              style={styles.sourceNameWrap}
            >
              <Text style={[styles.sourceName, { color: theme.colors.accent }]} numberOfLines={1}>
                {source.name}
              </Text>
            </Pressable>
            <View style={styles.sourceBadges}>
              {source.avoided ? (
                <Badge variant="neutral">{i18n.t('sources.avoidedBadge')}</Badge>
              ) : null}
              {source.type === 'manual' && source.due ? (
                <Badge variant="warning">{i18n.t('sources.due')}</Badge>
              ) : null}
              <Badge variant={source.health === 'healthy' ? 'success' : 'danger'}>
                {source.health}
              </Badge>
            </View>
          </View>

          <Text style={[styles.metaText, { color: theme.colors.textMuted }]}>
            {i18n.t(SOURCE_TYPE_KEYS[source.type] ?? source.type)} · {i18n.t('common.jobs')}:{' '}
            {source.jobs_count ?? '—'} · {i18n.t('sources.lastScraped')}:{' '}
            {source.last_scraped ? shortDate(source.last_scraped, dateLocale(i18n.lang)) : '—'}
          </Text>

          {source.avoided && source.avoid_reason ? (
            <Text style={[styles.metaText, { color: theme.colors.textMuted }]} numberOfLines={2}>
              {i18n.t('sources.avoidReasonLabel')}: {source.avoid_reason}
            </Text>
          ) : null}

          {source.type === 'manual' && source.next_check_at ? (
            <Text style={[styles.metaText, { color: theme.colors.textMuted }]}>
              {i18n.t('sources.nextCheck')}:{' '}
              {shortDate(source.next_check_at, dateLocale(i18n.lang))}
              {dueText(source) ? ` — ${dueText(source)}` : ''}
            </Text>
          ) : null}

          <View style={styles.sourceActions}>
            {source.type === 'manual' ? (
              <>
                <Button variant="ghost" size="sm" onPress={() => void Linking.openURL(source.url)}>
                  <Icon name="external-link" size={14} />
                  {i18n.t('sources.openBoard')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onPress={() => markChecked(source)}
                  loading={checkSource.isPending}
                >
                  <Icon name="circle-check" size={14} />
                  {i18n.t('sources.markChecked')}
                </Button>
              </>
            ) : null}
            {source.type !== 'manual' ? (
              <Button variant="ghost" size="sm" onPress={() => setAuthSource(source)}>
                <Icon name="settings" size={14} />
                {i18n.t('common.auth')}
              </Button>
            ) : null}
            <Button variant="ghost" size="sm" onPress={() => openEdit(source)}>
              <Icon name="pencil" size={14} />
              {i18n.t('common.edit')}
            </Button>
            {/* Quick toggle; the reason itself is edited in the form. */}
            <Button
              variant="ghost"
              size="sm"
              onPress={() => toggleAvoided(source)}
              loading={setSourceAvoided.isPending}
            >
              <Icon name={source.avoided ? 'eye' : 'eye-off'} size={14} />
              {i18n.t(source.avoided ? 'sources.restoreSource' : 'sources.avoidOnly')}
            </Button>
            <Button variant="danger" size="sm" onPress={() => void remove(source)}>
              <Icon name="trash" size={14} />
              {i18n.t('common.delete')}
            </Button>
          </View>
        </View>
      ))}

      {authSource ? (
        <SourceAuthModal source={authSource} onClose={() => setAuthSource(null)} />
      ) : null}
    </ScrollView>
  );
}

function SourceAuthModal({ source, onClose }: { source: Source; onClose: () => void }) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const { data: current } = useSourceAuth(source.id);
  const saveAuth = useSaveSourceAuth(source.id);
  const clearAuth = useClearSourceAuth(source.id);
  const testAuth = useTestSourceAuth(source.id);

  const [authType, setAuthType] = useState<'none' | 'token' | 'api_key'>('none');
  const [authToken, setAuthToken] = useState('');
  const [authApiKey, setAuthApiKey] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);

  const hasAuth = current?.has_auth ?? false;
  const secretMissing =
    (authType === 'token' && !authToken.trim()) || (authType === 'api_key' && !authApiKey.trim());

  const save = () => {
    const payload: { auth_type: 'none' | 'token' | 'api_key'; token?: string; api_key?: string } = {
      auth_type: authType,
    };
    if (authType === 'token') {
      payload.token = authToken;
    }
    if (authType === 'api_key') {
      payload.api_key = authApiKey;
    }
    saveAuth.mutate(payload, {
      onSuccess: () => {
        setAuthToken('');
        setAuthApiKey('');
        setTestResult(null);
        toast.success(i18n.t('sources.authSaved'));
      },
      onError: () => toast.error(i18n.t('errors.failedSaveAuth')),
    });
  };

  const test = () => {
    setTestResult(null);
    testAuth.mutate(undefined, {
      onSuccess: (result) => {
        setTestResult(result);
        toast.success(result.ok ? i18n.t('sources.authOk') : i18n.t('sources.authFailed'));
      },
      onError: () => toast.error(i18n.t('errors.failedRunAuthTest')),
    });
  };

  const clear = () => {
    clearAuth.mutate(undefined, {
      onSuccess: () => {
        setAuthType('none');
        setAuthToken('');
        setAuthApiKey('');
        setTestResult(null);
        toast.success(i18n.t('sources.authCleared'));
      },
      onError: () => toast.error(i18n.t('errors.failedClearAuth')),
    });
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <ScrollView
          style={[
            styles.modalCard,
            { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
          ]}
          contentContainerStyle={styles.modalContent}
        >
          <Text style={[styles.modalTitle, { color: theme.colors.text }]}>{source.name}</Text>
          <Text style={[styles.modalSub, { color: theme.colors.textMuted }]}>
            {i18n.t('sources.authenticationTitle')}
          </Text>

          <FormField label={i18n.t('sources.authType')}>
            <Select
              value={authType}
              options={[
                { label: i18n.t('sources.authNone'), value: 'none' },
                { label: i18n.t('sources.authToken'), value: 'token' },
                { label: i18n.t('sources.authApiKey'), value: 'api_key' },
              ]}
              onValueChange={(value) => setAuthType(value)}
            />
          </FormField>

          {authType === 'token' ? (
            <FormField label={i18n.t('sources.authToken')}>
              <Input
                value={authToken}
                onChangeText={setAuthToken}
                placeholder={i18n.t('sources.authTokenPlaceholder')}
                autoCapitalize="none"
              />
            </FormField>
          ) : null}

          {authType === 'api_key' ? (
            <FormField label={i18n.t('sources.authApiKey')}>
              <Input
                value={authApiKey}
                onChangeText={setAuthApiKey}
                placeholder={i18n.t('sources.authApiKeyPlaceholder')}
                autoCapitalize="none"
              />
            </FormField>
          ) : null}

          {testResult ? (
            <Alert tone={testResult.ok ? 'success' : 'error'}>
              {testResult.ok
                ? i18n.t('sources.authOk')
                : (testResult.error ?? i18n.t('sources.authFailed'))}
            </Alert>
          ) : null}

          <View style={styles.modalActions}>
            {hasAuth && current?.auth_type !== 'none' ? (
              <Button variant="ghost" onPress={clear}>
                {i18n.t('sources.clearAuth')}
              </Button>
            ) : null}
            <Button
              variant="ghost"
              onPress={test}
              loading={testAuth.isPending}
              disabled={authType === 'none' && !hasAuth}
            >
              <Icon name="activity" size={14} />
              {testAuth.isPending ? i18n.t('sources.testing') : i18n.t('sources.testConnection')}
            </Button>
            <Button onPress={save} loading={saveAuth.isPending} disabled={secretMissing}>
              {saveAuth.isPending ? i18n.t('sources.saving') : i18n.t('common.save')}
            </Button>
          </View>
        </ScrollView>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    gap: 4,
    marginBottom: 12,
  },
  formTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 6,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowField: {
    flex: 1,
  },
  switchWrap: {
    flex: 1,
    justifyContent: 'center',
  },
  hint: {
    fontSize: 12,
    marginTop: -6,
  },
  code: {
    fontFamily: 'monospace',
  },
  formActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 8,
  },
  sourceCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    gap: 8,
    marginBottom: 10,
  },
  /** Mirrors the web `.is-avoided` dimming — kept legible, just visually demoted. */
  avoidedCard: {
    opacity: 0.6,
  },
  sourceHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  sourceNameWrap: {
    flex: 1,
  },
  sourceBadges: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sourceName: {
    fontSize: 15,
    fontWeight: '600',
  },
  metaText: {
    fontSize: 13,
  },
  sourceActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 2,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.5)',
    justifyContent: 'center',
    padding: 24,
  },
  modalCard: {
    borderRadius: 14,
    borderWidth: 1,
    maxHeight: '80%',
  },
  modalContent: {
    padding: 20,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  modalSub: {
    fontSize: 13,
    marginTop: 2,
    marginBottom: 10,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 12,
    flexWrap: 'wrap',
  },
});
