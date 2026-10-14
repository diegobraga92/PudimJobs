import { StyleSheet, Text, View } from 'react-native';

import { Badge } from '@/components/ui/Badge';
import { Tag } from '@/components/ui/Tag';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { AtsReport } from '@/types';
import { factorPercent, deterministicScore, scoreVariant } from '@/utils/ats';

/** Read-only ATS report (ADR 013) — the mobile analog of the web `app-ats-report` component. */
export function AtsReportView({ report }: { report: AtsReport }) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const headline = deterministicScore(report);
  const method =
    report.method === 'hybrid' ? i18n.t('cv.ats.methodHybrid') : i18n.t('cv.ats.methodHeuristic');

  return (
    <View style={styles.wrap}>
      <View style={styles.scoreRow}>
        <Text
          style={[
            styles.score,
            {
              color:
                headline >= 75
                  ? theme.colors.success
                  : headline >= 50
                    ? theme.colors.warning
                    : theme.colors.danger,
              borderColor:
                headline >= 75
                  ? theme.colors.success
                  : headline >= 50
                    ? theme.colors.warning
                    : theme.colors.danger,
            },
          ]}
        >
          {headline}
        </Text>
        <View style={styles.scoreTags}>
          <Badge variant={scoreVariant(headline)}>{i18n.t('cv.ats.deterministic')}</Badge>
          {report.llm_score != null ? (
            <Badge variant={scoreVariant(report.llm_score)}>
              {i18n.t('cv.ats.llm', { score: report.llm_score })}
            </Badge>
          ) : null}
          <Text style={[styles.muted, { color: theme.colors.textMuted }]}>{method}</Text>
        </View>
      </View>

      {report.factors.map((factor) => (
        <View key={factor.key} style={styles.factor}>
          <View style={styles.factorHead}>
            <Text style={[styles.factorLabel, { color: theme.colors.textSecondary }]}>
              {factor.label}
            </Text>
            <Text style={[styles.muted, { color: theme.colors.textMuted }]}>
              {factorPercent(factor.score)}%
            </Text>
          </View>
          <View style={[styles.bar, { backgroundColor: theme.colors.surfaceMuted }]}>
            <View
              style={[
                styles.barFill,
                { width: `${factorPercent(factor.score)}%`, backgroundColor: theme.colors.accent },
              ]}
            />
          </View>
          <Text style={[styles.muted, { color: theme.colors.textMuted }]}>{factor.detail}</Text>
        </View>
      ))}

      {report.matched_skills.length > 0 ? (
        <>
          <Text style={[styles.sub, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.matchedSkills')}
          </Text>
          <View style={styles.chips}>
            {report.matched_skills.map((skill) => (
              <Tag key={skill}>{skill}</Tag>
            ))}
          </View>
        </>
      ) : null}

      {report.missing_skills.length > 0 ? (
        <>
          <Text style={[styles.sub, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.missingSkills')}
          </Text>
          <View style={styles.chips}>
            {report.missing_skills.map((skill) => (
              <Tag key={skill}>{skill}</Tag>
            ))}
          </View>
        </>
      ) : null}

      {report.recommendations.length > 0 ? (
        <>
          <Text style={[styles.sub, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.recommendations')}
          </Text>
          {report.recommendations.map((tip) => (
            <Text key={tip} style={[styles.bullet, { color: theme.colors.textSecondary }]}>
              • {tip}
            </Text>
          ))}
        </>
      ) : null}

      {report.warnings.length > 0 ? (
        <>
          <Text style={[styles.sub, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.warnings')}
          </Text>
          {report.warnings.map((warning) => (
            <Text key={warning} style={[styles.bullet, { color: theme.colors.warning }]}>
              • {warning}
            </Text>
          ))}
        </>
      ) : null}

      {report.llm_summary ? (
        <>
          <Text style={[styles.sub, { color: theme.colors.textMuted }]}>
            {i18n.t('cv.ats.llmSummary')}
          </Text>
          <Text style={[styles.bullet, { color: theme.colors.textSecondary }]}>
            {report.llm_summary}
          </Text>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 6,
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 4,
  },
  /** The deterministic headline plus its labels (and the AI's own estimate). */
  scoreTags: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
  },
  score: {
    width: 48,
    height: 48,
    borderRadius: 9999,
    borderWidth: 3,
    textAlign: 'center',
    textAlignVertical: 'center',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 42,
  },
  factor: {
    gap: 3,
  },
  factorHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  factorLabel: {
    fontSize: 13,
  },
  bar: {
    height: 6,
    borderRadius: 9999,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
  },
  sub: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    marginTop: 8,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  muted: {
    fontSize: 12,
  },
  bullet: {
    fontSize: 13,
    lineHeight: 19,
  },
});
