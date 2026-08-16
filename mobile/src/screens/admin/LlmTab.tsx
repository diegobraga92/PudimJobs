import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { Switch } from '@/components/ui/Switch';
import { useToast } from '@/components/toast/ToastProvider';
import { useLlmConfig, useTestLlmConfig, useUpdateLlmConfig } from '@/hooks/useAdmin';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

/** Admin LLM tab — model provider configuration with a connection test. */
export function LlmTab() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const { data: config } = useLlmConfig();
  const updateConfig = useUpdateLlmConfig();
  const testConfig = useTestLlmConfig();

  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
  const [model, setModel] = useState('gpt-4o-mini');
  const [apiKey, setApiKey] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);

  // Load the persisted config into the form the first time it arrives.
  if (config && config.id !== loadedId) {
    setLoadedId(config.id);
    setEnabled(config.enabled);
    setBaseUrl(config.base_url);
    setModel(config.model);
  }

  const save = () => {
    updateConfig.mutate(
      { enabled, base_url: baseUrl, model, api_key: apiKey || undefined },
      {
        onSuccess: () => {
          setApiKey('');
          toast.success(i18n.t('admin.llmSaved'));
        },
        onError: () => toast.error(i18n.t('errors.failedSaveLlm')),
      },
    );
  };

  const test = () => {
    setTestResult(null);
    testConfig.mutate(undefined, {
      onSuccess: (result) => {
        setTestResult(result);
        toast.success(result.ok ? i18n.t('admin.llmOk') : i18n.t('admin.llmFailed'));
      },
      onError: () => toast.error(i18n.t('errors.failedRunLlmTest')),
    });
  };

  return (
    <View style={styles.container}>
      <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('admin.llmTitle')}</Text>
      <Text style={[styles.intro, { color: theme.colors.textMuted }]}>{i18n.t('admin.llmIntro')}</Text>

      <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
        <View style={styles.toggleRow}>
          <Text style={[styles.toggleLabel, { color: theme.colors.text }]}>{i18n.t('admin.enableLlm')}</Text>
          <Switch value={enabled} onValueChange={setEnabled} />
        </View>

        <FormField label={i18n.t('admin.baseUrl')}>
          <Input value={baseUrl} onChangeText={setBaseUrl} placeholder="https://api.openai.com/v1" autoCapitalize="none" />
        </FormField>

        <FormField label={i18n.t('admin.model')}>
          <Input value={model} onChangeText={setModel} placeholder="gpt-4o-mini" />
        </FormField>

        <FormField label={`${i18n.t('admin.apiKey')}${config?.api_key_masked ? ` (${i18n.t('admin.stored')} ${config.api_key_masked})` : ` (${i18n.t('admin.notSet')})`}`}>
          <Input value={apiKey} onChangeText={setApiKey} placeholder="sk-…" autoCapitalize="none" secureTextEntry />
        </FormField>

        {testResult ? (
          <Alert tone={testResult.ok ? 'success' : 'error'}>
            {testResult.ok ? i18n.t('admin.llmOk') : testResult.error ?? i18n.t('admin.connectionFailed')}
          </Alert>
        ) : null}

        <View style={styles.actions}>
          <Button variant="ghost" onPress={() => setLoadedId(null)} disabled={updateConfig.isPending}>
            {i18n.t('admin.reset')}
          </Button>
          <Button variant="ghost" onPress={test} loading={testConfig.isPending} disabled={!enabled}>
            {testConfig.isPending ? i18n.t('admin.testing') : i18n.t('admin.testConnection')}
          </Button>
          <Button onPress={save} loading={updateConfig.isPending}>
            {updateConfig.isPending ? i18n.t('admin.saving') : i18n.t('admin.save')}
          </Button>
        </View>
      </View>
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
  intro: {
    fontSize: 14,
    lineHeight: 20,
  },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    gap: 6,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  toggleLabel: {
    fontSize: 14,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 10,
    flexWrap: 'wrap',
  },
});
