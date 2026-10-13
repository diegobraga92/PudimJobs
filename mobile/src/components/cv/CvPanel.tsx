import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AtsReportView } from '@/components/cv/AtsReportView';
import { CvPreview } from '@/components/cv-preview/CvPreview';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/icons/Icon';
import { Panel } from '@/components/ui/Panel';
import { Skeleton } from '@/components/ui/Skeleton';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import { useUpdateApplication } from '@/hooks/useApplications';
import { useAtsScore, useDeleteGeneratedCv, useGeneratedCvs } from '@/hooks/useCv';
import { useTailorCv } from '@/hooks/useJobs';
import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationsStackParamList } from '@/navigation/types';
import { useAuthStore } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';
import { AtsReport, GeneratedCV } from '@/types';
import { scoreVariant } from '@/utils/ats';
import { variantLabelKey } from '@/utils/cv';
import { dateLocale, shortDate } from '@/utils/dates';
import { displayNameFromEmail } from '@/utils/names';
import { sharePdfFromUrl } from '@/utils/pdf';

/**
 * Per-job tailored-CV workspace.
 *
 * Merges the two things that used to live apart on the Master CV screen: the CV
 * tailored for a job and its ATS check. Dropped into the application workspace
 * so "the CV I sent, and how it scores" sits next to the application.
 *
 * Tailoring is asynchronous (`POST /api/jobs/{id}/tailor` → 202 + Celery), so
 * enqueueing flips the panel into a pending state resolved with "Refresh".
 */
export function CvPanel({
  jobId,
  applicationId,
  linkedCvId,
}: {
  jobId: string;
  applicationId?: string;
  /** `Application.generated_cv_id` — the artifact recorded as sent (badge). */
  linkedCvId?: string | null;
}) {
  const { theme } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<ApplicationsStackParamList>>();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const user = useAuthStore((state) => state.user);

  const { data: tailored = [], isPending, refetch } = useGeneratedCvs(jobId);
  const tailor = useTailorCv();
  const score = useAtsScore();
  const deleteGenerated = useDeleteGeneratedCv();
  const linkVariant = useUpdateApplication(applicationId ?? '');

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [report, setReport] = useState<AtsReport | null>(null);
  const [reportFor, setReportFor] = useState<string | null>(null);

  const selected = tailored.find((item) => item.id === selectedId) ?? tailored[0] ?? null;
  // A freshly computed report wins over the one cached on the artifact.
  const activeReport =
    reportFor && reportFor === selected?.id ? report : (selected?.ats_report ?? null);

  const isItemLinked = (item: GeneratedCV | null): boolean =>
    !!linkedCvId && !!item && item.id === linkedCvId;
  const isLinked = isItemLinked(selected);

  /** Record an artifact as the CV actually sent with the application (ADR 016). */
  const markAsSent = (item: GeneratedCV) => {
    if (!applicationId || isItemLinked(item)) {
      return;
    }
    linkVariant.mutate(
      { generated_cv_id: item.id },
      {
        onSuccess: () => toast.success(i18n.t('cv.panel.sentRecorded')),
        onError: () => toast.error(i18n.t('errors.failedUpdateApplication')),
      },
    );
  };

  /** Open the artifact's own editor (never the master CV — ADR 016). */
  const edit = (item: GeneratedCV) => navigation.navigate('TailoredCvEditor', { id: item.id });

  /** Enqueue a tailoring run for this job (linked to the application, if any). */
  const runTailor = () => {
    tailor.mutate(
      { id: jobId, applicationId },
      {
        onSuccess: () => {
          setPending(true);
          toast.success(i18n.t('cv.panel.enqueued'));
        },
        onError: () => toast.error(i18n.t('errors.failedTailorCV')),
      },
    );
  };

  /** Re-fetch this job's tailored CVs and clear the pending state if it landed. */
  const refresh = async () => {
    const result = await refetch();
    if ((result.data ?? []).length > 0) {
      setPending(false);
    }
  };

  const runScore = () => {
    const structure = selected?.structured_json;
    if (!selected || !structure) {
      return;
    }
    score.mutate(
      { cv: structure, job_id: jobId, generated_cv_id: selected.id },
      {
        onSuccess: (result) => {
          setReport(result);
          setReportFor(selected.id);
          toast.success(i18n.t('cv.ats.scored', { score: result.score, method: result.method }));
        },
        onError: () => toast.error(i18n.t('errors.failedAtsScore')),
      },
    );
  };

  const download = () => {
    if (!selected) {
      return;
    }
    sharePdfFromUrl(`/api/cv/generated/${selected.id}/pdf`, `tailored-cv-${selected.id}.pdf`).catch(
      () => toast.error(i18n.t('errors.failedDownloadPdf')),
    );
  };

  const remove = async () => {
    if (!selected) {
      return;
    }
    const confirmed = await confirm.confirm({
      title: i18n.t('cv.deleteTailoredTitle'),
      message: i18n.t('cv.deleteTailoredMessage', {
        title: selected.job_title ?? selected.job_company ?? '',
      }),
      confirmLabel: i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteGenerated.mutate(selected.id, {
      onSuccess: () => {
        setSelectedId(null);
        toast.success(i18n.t('cv.tailoredDeleted'));
      },
      onError: () => toast.error(i18n.t('errors.failedDeleteGeneratedCV')),
    });
  };

  return (
    <Panel style={styles.panel}>
      <View style={styles.head}>
        <Text style={[styles.title, { color: theme.colors.primary }]}>
          {i18n.t('cv.panel.title')}
        </Text>
        <View style={styles.headActions}>
          <Button variant="ghost" size="sm" onPress={() => void refresh()}>
            <Icon name="refresh" size={14} color={theme.colors.textSecondary} />
            {i18n.t('cv.panel.refresh')}
          </Button>
          <Button variant="accent" size="sm" onPress={runTailor} loading={tailor.isPending}>
            {tailored.length > 0 ? i18n.t('cv.panel.retailor') : i18n.t('cv.panel.tailor')}
          </Button>
        </View>
      </View>

      {pending ? <Alert tone="info">{i18n.t('cv.panel.pending')}</Alert> : null}

      {isPending ? <Skeleton width="60%" height={16} /> : null}

      {!isPending && tailored.length === 0 ? (
        <EmptyState
          icon="file-text"
          title={i18n.t('cv.panel.emptyTitle')}
          hint={i18n.t('cv.panel.emptyHint')}
        />
      ) : null}

      {selected ? (
        <View style={styles.body}>
          {tailored.length > 1 ? (
            <View style={styles.variantList}>
              {tailored.map((item) => (
                <Pressable
                  key={item.id}
                  accessibilityRole="button"
                  accessibilityState={{ selected: item.id === selected.id }}
                  onPress={() => setSelectedId(item.id)}
                  style={[
                    styles.variantCard,
                    { borderColor: item.id === selected.id ? theme.colors.accent : theme.colors.border },
                  ]}
                >
                  <Text style={[styles.variantName, { color: theme.colors.text }]}>
                    {i18n.t(variantLabelKey(item.variant))}
                  </Text>
                  {isItemLinked(item) ? (
                    <Badge variant="info">{i18n.t('cv.panel.linked')}</Badge>
                  ) : null}
                  {item.ats_score !== null ? (
                    <Badge variant={scoreVariant(item.ats_score)}>
                      {i18n.t('cv.ats.scoreBadge', { score: item.ats_score })}
                    </Badge>
                  ) : null}
                </Pressable>
              ))}
            </View>
          ) : null}

          {tailored.length === 1 && tailored[0].variant === 'rule' ? (
            <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
              {i18n.t('cv.panel.llmVariantOff')}
            </Text>
          ) : null}

          <View style={styles.meta}>
            <Text style={[styles.variantName, { color: theme.colors.text }]}>
              {i18n.t(variantLabelKey(selected.variant))}
            </Text>
            <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
              {shortDate(selected.created_at, dateLocale(i18n.lang))}
            </Text>
            {isLinked ? <Badge variant="info">{i18n.t('cv.panel.linked')}</Badge> : null}
            {selected.ats_score !== null ? (
              <Badge variant={scoreVariant(selected.ats_score)}>
                {i18n.t('cv.ats.scoreBadge', { score: selected.ats_score })}
              </Badge>
            ) : null}
          </View>

          {selected.ats_report?.llm_self_score != null ? (
            <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
              {i18n.t('cv.panel.llmSelfScore', { score: selected.ats_report.llm_self_score })}
            </Text>
          ) : null}

          <View style={styles.actions}>
            <Button variant="ghost" size="sm" onPress={download}>
              <Icon name="download" size={14} color={theme.colors.textSecondary} />
              {i18n.t('cv.pdf')}
            </Button>
            {applicationId ? (
              <Button
                variant="ghost"
                size="sm"
                onPress={() => markAsSent(selected)}
                disabled={isLinked}
              >
                <Icon
                  name="check"
                  size={14}
                  color={isLinked ? theme.colors.success : theme.colors.textSecondary}
                />
                {isLinked ? i18n.t('cv.panel.linked') : i18n.t('cv.panel.useThisOne')}
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onPress={() => edit(selected)}
              disabled={!selected.structured_json}
            >
              <Icon name="pencil" size={14} color={theme.colors.textSecondary} />
              {i18n.t('cv.panel.edit')}
            </Button>
            <Button variant="ghost" size="sm" onPress={() => void remove()}>
              <Icon name="trash" size={14} color={theme.colors.danger} />
            </Button>
          </View>

          {selected.structured_json ? (
            <CvPreview cv={selected.structured_json} name={displayNameFromEmail(user?.email)} />
          ) : (
            <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
              {i18n.t('cv.panel.noContent')}
            </Text>
          )}

          <Text style={[styles.sectionTitle, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.title')}
          </Text>
          <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.hint')}
          </Text>
          <Button
            variant="accent"
            size="sm"
            onPress={runScore}
            loading={score.isPending}
            disabled={!selected.structured_json}
          >
            {i18n.t('cv.ats.check')}
          </Button>

          {activeReport ? <AtsReportView report={activeReport} /> : null}
        </View>
      ) : null}
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: 12,
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
  },
  headActions: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
  },
  body: {
    gap: 10,
  },
  variantList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  /* One card per variant: deterministic vs AI rewrite (ADR 016). */
  variantCard: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderRadius: 8,
  },
  variantName: {
    fontSize: 13,
    fontWeight: '700',
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    marginTop: 6,
  },
  muted: {
    fontSize: 12,
  },
});
