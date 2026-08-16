import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { useI18n } from '@/i18n/I18nProvider';
import { useAuditActions, useAuditLog } from '@/hooks/useAdmin';
import { useTheme } from '@/theme/ThemeProvider';
import { AuditFilters } from '@/types';
import { dateLocale, shortDate } from '@/utils/dates';

/** Admin Audit tab — filterable audit log with expandable change details. */
export function AuditTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const { data: actions } = useAuditActions();
  const [draft, setDraft] = useState<{ action: string; entity: string; dateFrom: string; dateTo: string }>({
    action: '',
    entity: '',
    dateFrom: '',
    dateTo: '',
  });
  const [filters, setFilters] = useState<AuditFilters>({});
  const { data: entries = [], error } = useAuditLog(filters);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const apply = () => {
    setFilters({
      action: draft.action || undefined,
      entity_type: draft.entity || undefined,
      date_from: draft.dateFrom || undefined,
      date_to: draft.dateTo || undefined,
    });
  };

  const entityOptions = (actions?.entity_types ?? []).map((value) => ({ label: value, value }));
  const actionOptions = (actions?.actions ?? []).map((value) => ({ label: value, value }));

  return (
    <View style={styles.container}>
      <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('admin.auditLog')}</Text>

      <View style={[styles.filters, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
        <View style={styles.row}>
          <FormField label={i18n.t('admin.allActions')} style={styles.rowField}>
            <Select
              value={draft.action || null}
              options={actionOptions}
              onValueChange={(value) => setDraft((current) => ({ ...current, action: value }))}
              placeholder={i18n.t('admin.allActions')}
            />
          </FormField>
          <FormField label={i18n.t('admin.allEntityTypes')} style={styles.rowField}>
            <Select
              value={draft.entity || null}
              options={entityOptions}
              onValueChange={(value) => setDraft((current) => ({ ...current, entity: value }))}
              placeholder={i18n.t('admin.allEntityTypes')}
            />
          </FormField>
        </View>
        <View style={styles.row}>
          <FormField label={i18n.t('admin.fromDate')} style={styles.rowField}>
            <Input value={draft.dateFrom} onChangeText={(value) => setDraft((current) => ({ ...current, dateFrom: value }))} placeholder="YYYY-MM-DD" />
          </FormField>
          <FormField label={i18n.t('admin.toDate')} style={styles.rowField}>
            <Input value={draft.dateTo} onChangeText={(value) => setDraft((current) => ({ ...current, dateTo: value }))} placeholder="YYYY-MM-DD" />
          </FormField>
        </View>
        <Button size="sm" onPress={apply}>
          {i18n.t('jobs.search')}
        </Button>
      </View>

      {error ? <Alert tone="error">{i18n.t('errors.failedLoadAudit')}</Alert> : null}


      {entries.length === 0 ? (
        <Text style={[styles.empty, { color: theme.colors.textMuted }]}>{i18n.t('admin.noAuditEntries')}</Text>
      ) : (
        entries.map((entry) => {
          const expanded = expandedId === entry.id;
          return (
            <View key={entry.id} style={[styles.entry, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
              <Text style={[styles.entryTime, { color: theme.colors.textMuted }]}>{shortDate(entry.timestamp, dateLocale(i18n.lang))}</Text>
              <Text style={[styles.entryUser, { color: theme.colors.textSecondary }]}>{entry.email ?? entry.user_id ?? '—'}</Text>
              <Text style={[styles.actionTag, { color: theme.colors.primary }]}>{entry.action}</Text>
              <Text style={[styles.entryEntity, { color: theme.colors.textMuted }]}>
                {entry.entity_type}
                {entry.entity_id ? ` · ${entry.entity_id.slice(0, 8)}` : ''}
              </Text>
              <Pressable
                onPress={() => setExpandedId(expanded ? null : entry.id)}
                accessibilityRole="button"
                style={styles.detailsBtn}
              >
                <Text style={[styles.detailsText, { color: theme.colors.accent }]}>
                  {expanded ? i18n.t('admin.hide') : i18n.t('admin.details')}
                </Text>
              </Pressable>
              {expanded && entry.changes ? (
                <Text style={[styles.changes, { color: theme.colors.textSecondary }]}>
                  {JSON.stringify(entry.changes, null, 2)}
                </Text>
              ) : null}
            </View>
          );
        })
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  filters: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowField: {
    flex: 1,
  },
  empty: {
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 12,
  },
  entry: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 3,
  },
  entryTime: {
    fontSize: 12,
  },
  entryUser: {
    fontSize: 13,
  },
  actionTag: {
    fontSize: 13,
    fontWeight: '700',
    alignSelf: 'flex-start',
  },
  entryEntity: {
    fontSize: 12,
  },
  detailsBtn: {
    alignSelf: 'flex-start',
    paddingVertical: 4,
  },
  detailsText: {
    fontSize: 13,
    fontWeight: '600',
  },
  changes: {
    fontSize: 12,
    fontFamily: 'monospace',
  },
});

