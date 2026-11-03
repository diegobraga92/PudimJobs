import { StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { TextArea } from '@/components/ui/TextArea';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

/** The job fields a person can type by hand. */
export interface JobFields {
  title: string;
  company: string;
  location: string;
  url: string;
  posted_date: string;
  tags: string;
  description: string;
}

/**
 * Manual job form — the "Add job" panel on the Jobs page and the edit dialog on the
 * job page (ADR 026) share it, since both write the same fields through the same
 * validation: title and company are required (the API trims them and refuses a
 * blank), while everything else is optional.
 */
export function JobFieldsForm({
  fields,
  onChange,
  onCancel,
  onSave,
  saving,
  heading,
  submitLabel,
  hint,
  descriptionHint,
  error,
}: {
  fields: JobFields;
  onChange: (fields: JobFields) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
  heading: string;
  submitLabel: string;
  hint?: string;
  descriptionHint?: string;
  error?: string | null;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const set = (key: keyof JobFields, value: string) => onChange({ ...fields, [key]: value });
  const valid = fields.title.trim().length > 0 && fields.company.trim().length > 0;

  return (
    <View
      style={[
        styles.panel,
        { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
      ]}
    >
      <Text style={[styles.heading, { color: theme.colors.text }]}>{heading}</Text>
      {hint ? <Text style={[styles.hint, { color: theme.colors.textMuted }]}>{hint}</Text> : null}

      <FormField label={i18n.t('common.title')}>
        <Input
          value={fields.title}
          onChangeText={(value) => set('title', value)}
          placeholder={i18n.t('jobs.titlePlaceholder')}
        />
      </FormField>

      <FormField label={i18n.t('common.company')}>
        <Input
          value={fields.company}
          onChangeText={(value) => set('company', value)}
          placeholder="Acme"
        />
      </FormField>

      <FormField label={i18n.t('common.location')}>
        <Input
          value={fields.location}
          onChangeText={(value) => set('location', value)}
          placeholder={i18n.t('jobs.locationPlaceholder')}
        />
      </FormField>

      <FormField label={i18n.t('common.url')}>
        <Input
          value={fields.url}
          onChangeText={(value) => set('url', value)}
          placeholder="https://acme.example/jobs/1"
          autoCapitalize="none"
        />
      </FormField>

      <View style={styles.row}>
        <FormField label={i18n.t('jobs.postedDate')} style={styles.rowField}>
          <Input
            value={fields.posted_date}
            onChangeText={(value) => set('posted_date', value)}
            placeholder="YYYY-MM-DD"
          />
        </FormField>
        <FormField label={i18n.t('common.tags')} style={styles.rowField}>
          <Input
            value={fields.tags}
            onChangeText={(value) => set('tags', value)}
            placeholder="python, fastapi"
          />
        </FormField>
      </View>

      <FormField label={i18n.t('common.description')}>
        <TextArea
          value={fields.description}
          onChangeText={(value) => set('description', value)}
          placeholder={i18n.t('jobs.descriptionPlaceholder')}
          minHeight={140}
        />
      </FormField>
      {descriptionHint ? (
        <Text style={[styles.hint, styles.descriptionHint, { color: theme.colors.textMuted }]}>
          {descriptionHint}
        </Text>
      ) : null}

      {error ? <Alert tone="error">{error}</Alert> : null}

      <View style={styles.actions}>
        <Button variant="ghost" onPress={onCancel}>
          {i18n.t('common.cancel')}
        </Button>
        <Button onPress={onSave} disabled={!valid} loading={saving}>
          {submitLabel}
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    marginBottom: 12,
  },
  heading: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 10,
  },
  hint: {
    fontSize: 13,
    marginBottom: 10,
  },
  descriptionHint: {
    marginTop: -6,
    marginBottom: 10,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowField: {
    flex: 1,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 4,
  },
});
