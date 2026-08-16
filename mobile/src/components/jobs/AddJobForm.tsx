import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { TextArea } from '@/components/ui/TextArea';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

export interface AddJobFields {
  title: string;
  company: string;
  url: string;
  posted_date: string;
  tags: string;
  description: string;
}

/** Manual "Add job" form — mirrors the web form on the Jobs page. */
export function AddJobForm({
  fields,
  onChange,
  onCancel,
  onSave,
  saving,
}: {
  fields: AddJobFields;
  onChange: (fields: AddJobFields) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const set = (key: keyof AddJobFields, value: string) => onChange({ ...fields, [key]: value });
  const valid = fields.title.trim().length > 0 && fields.company.trim().length > 0;

  return (
    <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <Text style={[styles.heading, { color: theme.colors.text }]}>{i18n.t('jobs.addJobManually')}</Text>

      <FormField label={i18n.t('common.title')}>
        <Input value={fields.title} onChangeText={(value) => set('title', value)} placeholder={i18n.t('jobs.titlePlaceholder')} />
      </FormField>

      <FormField label={i18n.t('common.company')}>
        <Input value={fields.company} onChangeText={(value) => set('company', value)} placeholder="Acme" />
      </FormField>

      <FormField label={i18n.t('common.url')}>
        <Input value={fields.url} onChangeText={(value) => set('url', value)} placeholder="https://acme.example/jobs/1" autoCapitalize="none" />
      </FormField>

      <View style={styles.row}>
        <FormField label={i18n.t('jobs.postedDate')} style={styles.rowField}>
          <Input value={fields.posted_date} onChangeText={(value) => set('posted_date', value)} placeholder="YYYY-MM-DD" />
        </FormField>
        <FormField label={i18n.t('common.tags')} style={styles.rowField}>
          <Input value={fields.tags} onChangeText={(value) => set('tags', value)} placeholder="python, fastapi" />
        </FormField>
      </View>

      <FormField label={i18n.t('common.description')}>
        <TextArea
          value={fields.description}
          onChangeText={(value) => set('description', value)}
          placeholder={i18n.t('jobs.descriptionPlaceholder')}
          minHeight={100}
        />
      </FormField>

      <View style={styles.actions}>
        <Button variant="ghost" onPress={onCancel}>
          {i18n.t('common.cancel')}
        </Button>
        <Button onPress={onSave} disabled={!valid} loading={saving}>
          {i18n.t('jobs.addJob')}
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
