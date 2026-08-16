import { StyleSheet, Switch as RNSwitch, Text, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { Icon } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

export interface SearchFields {
  q: string;
  company: string;
  tags: string;
  date_from: string;
  date_to: string;
}

function TextSwitch({
  label,
  value,
  onValueChange,
}: {
  label: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
}) {
  const { theme } = useTheme();
  return (
    <View style={styles.switchRow}>
      <RNSwitch
        value={value}
        onValueChange={onValueChange}
        thumbColor={theme.colors.onPrimary}
        trackColor={{ false: theme.colors.borderStrong, true: theme.colors.primary }}
      />
      <Text style={[styles.switchLabel, { color: theme.colors.text }]}>{label}</Text>
    </View>
  );
}

/** Search bar — mirrors the web `.search-bar` form on the Jobs page. */
export function SearchForm({
  fields,
  onChange,
  hideApplied,
  showHidden,
  onToggleHideApplied,
  onToggleShowHidden,
  onSearch,
  searching,
}: {
  fields: SearchFields;
  onChange: (fields: SearchFields) => void;
  hideApplied: boolean;
  showHidden: boolean;
  onToggleHideApplied: () => void;
  onToggleShowHidden: () => void;
  onSearch: () => void;
  searching: boolean;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const set = (key: keyof SearchFields, value: string) => onChange({ ...fields, [key]: value });

  return (
    <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <FormField label={i18n.t('jobs.searchKeywordsPlaceholder')}>
        <View style={styles.searchWrap}>
          <Icon name="search" size={17} color={theme.colors.textFaint} />
          <Input
            style={styles.searchInput}
            value={fields.q}
            onChangeText={(value) => set('q', value)}
            placeholder={i18n.t('jobs.searchKeywordsPlaceholder')}
          />
        </View>
      </FormField>

      <FormField label={i18n.t('common.company')}>
        <Input
          value={fields.company}
          onChangeText={(value) => set('company', value)}
          placeholder={i18n.t('common.company')}
        />
      </FormField>

      <FormField label={i18n.t('jobs.tagsPlaceholder')}>
        <Input
          value={fields.tags}
          onChangeText={(value) => set('tags', value)}
          placeholder={i18n.t('jobs.tagsPlaceholder')}
        />
      </FormField>

      <View style={styles.row}>
        <FormField label={i18n.t('jobs.aria.afterDate')} style={styles.rowField}>
          <Input
            value={fields.date_from}
            onChangeText={(value) => set('date_from', value)}
            placeholder="YYYY-MM-DD"
          />
        </FormField>
        <FormField label={i18n.t('jobs.aria.beforeDate')} style={styles.rowField}>
          <Input
            value={fields.date_to}
            onChangeText={(value) => set('date_to', value)}
            placeholder="YYYY-MM-DD"
          />
        </FormField>
      </View>

      <View style={styles.toggles}>
        <TextSwitch label={i18n.t('jobs.hideApplied')} value={hideApplied} onValueChange={onToggleHideApplied} />
        <TextSwitch label={i18n.t('jobs.showHidden')} value={showHidden} onValueChange={onToggleShowHidden} />
      </View>

      <Button onPress={onSearch} loading={searching} fullWidth>
        {searching ? i18n.t('jobs.searching') : i18n.t('jobs.search')}
      </Button>
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
  searchWrap: {
    justifyContent: 'center',
  },
  searchInput: {
    paddingLeft: 36,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowField: {
    flex: 1,
  },
  toggles: {
    marginTop: 4,
    marginBottom: 8,
    gap: 8,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  switchLabel: {
    fontSize: 14,
  },
});
