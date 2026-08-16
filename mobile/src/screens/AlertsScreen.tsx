import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { FormField } from '@/components/ui/FormField';
import { Icon } from '@/components/icons/Icon';
import { Input } from '@/components/ui/Input';
import { Switch } from '@/components/ui/Switch';
import { Tag } from '@/components/ui/Tag';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import { useAlertRules, useDeleteAlertRule, useSaveAlertRule } from '@/hooks/useAlerts';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { AlertRule } from '@/types';
import { parseList } from '@/utils/lists';

interface AlertFormState {
  name: string;
  keywordsText: string;
  companiesText: string;
  tagsText: string;
  minYears: string;
  channelsText: string;
  remote_only: boolean;
  active: boolean;
}

const EMPTY_FORM: AlertFormState = {
  name: '',
  keywordsText: '',
  companiesText: '',
  tagsText: '',
  minYears: '',
  channelsText: 'in_app',
  remote_only: false,
  active: true,
};

/** Alert rules — mirrors the web alerts page (form + list with active toggle). */
export function AlertsScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: rules = [], isPending, error } = useAlertRules();
  const saveRule = useSaveAlertRule();
  const deleteRule = useDeleteAlertRule();

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AlertFormState>(EMPTY_FORM);

  const update = <K extends keyof AlertFormState>(key: K, value: AlertFormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const openEdit = (rule: AlertRule) => {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      keywordsText: rule.keywords.join(', '),
      companiesText: rule.companies.join(', '),
      tagsText: rule.tags.join(', '),
      minYears: rule.min_years_experience !== null ? String(rule.min_years_experience) : '',
      channelsText: rule.channels.join(', '),
      remote_only: rule.remote_only,
      active: rule.active,
    });
    setShowForm(true);
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditingId(null);
  };

  const save = () => {
    if (!form.name.trim()) {
      return;
    }
    const payload = {
      name: form.name,
      keywords: parseList(form.keywordsText),
      companies: parseList(form.companiesText),
      tags: parseList(form.tagsText),
      remote_only: form.remote_only,
      min_years_experience: form.minYears ? Number(form.minYears) : null,
      channels: parseList(form.channelsText),
      active: form.active,
    };
    saveRule.mutate(
      { id: editingId ?? undefined, payload },
      {
        onSuccess: () => {
          const wasEditing = !!editingId;
          setShowForm(false);
          setEditingId(null);
          toast.success(wasEditing ? i18n.t('alerts.updated') : i18n.t('alerts.created'));
        },
        onError: () => toast.error(i18n.t('errors.failedSaveAlert')),
      },
    );
  };

  const toggleActive = (rule: AlertRule) => {
    saveRule.mutate(
      { id: rule.id, payload: { active: !rule.active } },
      {
        onSuccess: () => {
          toast.success(rule.active ? i18n.t('alerts.pausedToast') : i18n.t('alerts.activatedToast'));
        },
        onError: () => toast.error(i18n.t('errors.failedUpdateRule')),
      },
    );
  };

  const remove = async (rule: AlertRule) => {
    const confirmed = await confirm.confirm({
      title: i18n.t('alerts.deleteTitle'),
      message: i18n.t('alerts.deleteMessage', { name: rule.name }),
      confirmLabel: i18n.t('common.delete'),
      cancelLabel: i18n.t('alerts.keepAlert'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteRule.mutate(rule.id, {
      onSuccess: () => toast.success(i18n.t('alerts.deletedToast')),
      onError: () => toast.error(i18n.t('errors.failedDeleteAlert')),
    });
  };


  return (
    <ScrollView style={[styles.container, { backgroundColor: theme.colors.bg }]} contentContainerStyle={styles.content}>
      <View style={styles.head}>
        <Text style={[styles.title, { color: theme.colors.text }]}>{i18n.t('alerts.title')}</Text>
        <Button size="sm" onPress={openCreate}>
          <Icon name="plus" size={16} />
          {i18n.t('alerts.newAlert')}
        </Button>
      </View>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadAlerts')}</Alert> : null}

      {showForm ? (
        <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <Text style={[styles.formTitle, { color: theme.colors.text }]}>
            {editingId ? i18n.t('alerts.editAlert') : i18n.t('alerts.newAlert')}
          </Text>

          <FormField label={i18n.t('common.name')}>
            <Input value={form.name} onChangeText={(value) => update('name', value)} placeholder="Senior Python jobs" />
          </FormField>

          <View style={styles.row}>
            <FormField label={i18n.t('alerts.keywords')} style={styles.rowField}>
              <Input value={form.keywordsText} onChangeText={(value) => update('keywordsText', value)} placeholder="python, fastapi" />
            </FormField>
            <FormField label={i18n.t('alerts.companies')} style={styles.rowField}>
              <Input value={form.companiesText} onChangeText={(value) => update('companiesText', value)} placeholder="Acme, Globex" />
            </FormField>
          </View>

          <View style={styles.row}>
            <FormField label={i18n.t('alerts.tags')} style={styles.rowField}>
              <Input value={form.tagsText} onChangeText={(value) => update('tagsText', value)} placeholder="backend, remote" />
            </FormField>
            <FormField label={i18n.t('alerts.minYears')} style={styles.rowField}>
              <Input value={form.minYears} onChangeText={(value) => update('minYears', value)} keyboardType="number-pad" placeholder="0" />
            </FormField>
          </View>

          <FormField label={i18n.t('alerts.channels')}>
            <Input value={form.channelsText} onChangeText={(value) => update('channelsText', value)} placeholder="in_app, email" />
          </FormField>

          <View style={styles.toggles}>
            <View style={styles.toggleRow}>
              <Text style={[styles.toggleLabel, { color: theme.colors.text }]}>{i18n.t('alerts.remoteOnly')}</Text>
              <Switch value={form.remote_only} onValueChange={(value) => update('remote_only', value)} />
            </View>
            <View style={styles.toggleRow}>
              <Text style={[styles.toggleLabel, { color: theme.colors.text }]}>{i18n.t('alerts.active')}</Text>
              <Switch value={form.active} onValueChange={(value) => update('active', value)} />
            </View>
          </View>

          <View style={styles.formActions}>
            <Button variant="ghost" onPress={cancelForm}>
              {i18n.t('common.cancel')}
            </Button>
            <Button onPress={save} disabled={!form.name.trim()} loading={saveRule.isPending}>
              {editingId ? i18n.t('alerts.saveChanges') : i18n.t('alerts.createAlert')}
            </Button>
          </View>
        </View>
      ) : null}

      {isPending ? (
        <Text style={[styles.loading, { color: theme.colors.textMuted }]}>{i18n.t('alerts.loading')}</Text>
      ) : null}

      {!isPending && rules.length === 0 ? (
        <EmptyState
          icon="bell"
          title={i18n.t('alerts.noRules')}
          hint={i18n.t('alerts.noRulesHint')}
          action={
            <Button onPress={openCreate}>
              <Icon name="plus" size={16} />
              {i18n.t('alerts.createOne')}
            </Button>
          }
        />
      ) : null}

      {rules.map((rule) => (
        <View key={rule.id} style={[styles.ruleCard, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <View style={styles.ruleHead}>
            <Text style={[styles.ruleName, { color: theme.colors.text }]}>{rule.name}</Text>
            <Button size="sm" variant={rule.active ? 'success' : 'ghost'} onPress={() => toggleActive(rule)}>
              {rule.active ? i18n.t('alerts.active') : i18n.t('alerts.paused')}
            </Button>
          </View>

          {rule.keywords.length > 0 ? (
            <View style={styles.tagsRow}>
              {rule.keywords.map((keyword) => (
                <Tag key={keyword}>{keyword}</Tag>
              ))}
            </View>
          ) : null}

          <Text style={[styles.meta, { color: theme.colors.textMuted }]}>
            {rule.companies.length > 0 ? `${i18n.t('alerts.companies')}: ${rule.companies.join(', ')}` : ''}
            {rule.companies.length > 0 && rule.channels.length > 0 ? ' · ' : ''}
            {rule.channels.length > 0 ? `${i18n.t('alerts.channels')}: ${rule.channels.join(', ')}` : ''}
            {rule.min_years_experience !== null ? ` · ${i18n.t('alerts.minYears')}: ${rule.min_years_experience}` : ''}
            {rule.remote_only ? ` · ${i18n.t('alerts.remoteOnly')}` : ''}
          </Text>

          <View style={styles.ruleActions}>
            <Button variant="ghost" size="sm" onPress={() => openEdit(rule)}>
              <Icon name="pencil" size={14} />
              {i18n.t('common.edit')}
            </Button>
            <Button variant="danger" size="sm" onPress={() => void remove(rule)}>
              <Icon name="trash" size={14} />
              {i18n.t('common.delete')}
            </Button>
          </View>
        </View>
      ))}
    </ScrollView>
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
  toggles: {
    gap: 8,
    marginVertical: 4,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  toggleLabel: {
    fontSize: 14,
  },
  formActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 8,
  },
  loading: {
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 16,
  },
  ruleCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    gap: 8,
    marginBottom: 10,
  },
  ruleHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  ruleName: {
    fontSize: 15,
    fontWeight: '600',
    flex: 1,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  meta: {
    fontSize: 13,
  },
  ruleActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 2,
  },
});
