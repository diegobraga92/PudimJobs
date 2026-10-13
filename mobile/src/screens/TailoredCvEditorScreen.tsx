import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppHeader } from '@/components/layout/AppHeader';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Icon } from '@/components/icons/Icon';
import { Input } from '@/components/ui/Input';
import { Panel } from '@/components/ui/Panel';
import { Skeleton } from '@/components/ui/Skeleton';
import { TextArea } from '@/components/ui/TextArea';
import { useToast } from '@/components/toast/ToastProvider';
import { useGeneratedCv, useUpdateGeneratedCv } from '@/hooks/useCv';
import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationsStackParamList } from '@/navigation/types';
import { useTheme } from '@/theme/ThemeProvider';
import { CVStructure, GeneratedCV } from '@/types';
import { variantLabelKey } from '@/utils/cv';

/**
 * Editor for a single tailored CV artifact (ADR 016).
 *
 * Edits land on the artifact itself (`PUT /api/cv/generated/{id}`), which
 * re-renders its PDF and clears the stale ATS cache. The master CV is never
 * touched, so tailored content can no longer leak into the version history.
 */
export function TailoredCvEditorScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const navigation = useNavigation<NativeStackNavigationProp<ApplicationsStackParamList>>();
  const route = useRoute<RouteProp<ApplicationsStackParamList, 'TailoredCvEditor'>>();
  const { id } = route.params;

  const { data: artifact, isPending, error } = useGeneratedCv(id);

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <AppHeader title={i18n.t('cv.panel.edit')} back onLeftPress={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={styles.content} style={styles.flex}>
        {error ? <Alert tone="error">{i18n.t('errors.failedLoadCV')}</Alert> : null}
        {isPending ? <Skeleton width="70%" height={20} /> : null}

        {artifact?.structured_json ? (
          <TailoredCvForm
            key={artifact.updated_at}
            artifact={artifact}
            structure={artifact.structured_json}
            onSaved={() => navigation.goBack()}
          />
        ) : null}
      </ScrollView>
    </View>
  );
}

/**
 * The editable surface: the fields tailoring actually touches (summary, skills
 * and experience bullet text). Everything else round-trips untouched.
 */
function TailoredCvForm({
  artifact,
  structure,
  onSaved,
}: {
  artifact: GeneratedCV;
  structure: CVStructure;
  onSaved: () => void;
}) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const update = useUpdateGeneratedCv(artifact.id);

  const [summary, setSummary] = useState(structure.summary ?? '');
  const [skillsText, setSkillsText] = useState((structure.skills ?? []).join(', '));
  const [bullets, setBullets] = useState<string[]>(
    (structure.experience ?? []).map((item) => (item.bullets ?? []).join('\n')),
  );

  const setBlockBullets = (index: number, value: string) =>
    setBullets((current) => current.map((text, i) => (i === index ? value : text)));

  const save = () => {
    const next: CVStructure = {
      ...structure,
      summary,
      skills: skillsText
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean),
      experience: (structure.experience ?? []).map((item, index) => ({
        ...item,
        bullets: (bullets[index] ?? '')
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
      })),
    };
    update.mutate(next, {
      onSuccess: () => {
        toast.success(i18n.t('cv.panel.editSaved'));
        onSaved();
      },
      onError: () => toast.error(i18n.t('errors.failedSaveCV')),
    });
  };

  return (
    <>
      <Panel style={styles.panel}>
        <Text style={[styles.company, { color: theme.colors.textMuted }]}>
          {artifact.job_title ?? artifact.job_company ?? ''}
        </Text>
        <View style={styles.metaRow}>
          <Icon name="wand" size={14} color={theme.colors.textSecondary} />
          <Text style={[styles.variant, { color: theme.colors.text }]}>
            {i18n.t(variantLabelKey(artifact.variant))}
          </Text>
        </View>
        <Text style={[styles.hint, { color: theme.colors.textMuted }]}>
          {i18n.t('cv.panel.editHint')}
        </Text>
      </Panel>

      <Panel style={styles.panel}>
        <FormField label={i18n.t('cv.panel.editSummary')}>
          <TextArea value={summary} onChangeText={setSummary} minHeight={90} />
        </FormField>

        <FormField label={i18n.t('cv.panel.editSkills')}>
          <Input
            value={skillsText}
            onChangeText={setSkillsText}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </FormField>
      </Panel>

      {(structure.experience ?? []).map((item, index) => (
        <Panel key={`${item.company}-${item.title}`} style={styles.panel}>
          <Text style={[styles.variant, { color: theme.colors.text }]}>
            {item.title} — {item.company}
          </Text>
          <FormField label={i18n.t('cv.panel.editBullets')}>
            <TextArea
              value={bullets[index] ?? ''}
              onChangeText={(value) => setBlockBullets(index, value)}
              minHeight={110}
            />
          </FormField>
        </Panel>
      ))}

      <View style={styles.actions}>
        <Button onPress={save} loading={update.isPending}>
          {i18n.t('cv.panel.editSave')}
        </Button>
        <Button variant="ghost" onPress={onSaved}>
          {i18n.t('common.cancel')}
        </Button>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
    gap: 12,
  },
  panel: {
    gap: 8,
  },
  company: {
    fontSize: 14,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  variant: {
    fontSize: 14,
    fontWeight: '700',
  },
  hint: {
    fontSize: 12,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
});
