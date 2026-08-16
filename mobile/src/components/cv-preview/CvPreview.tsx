import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { CVStructure } from '@/types';
import { dateLocale, formatDateRange } from '@/utils/dates';

/**
 * Renders a CVStructure as a clean A4-style document — mirrors the web
 * `app-cv-preview` component used by the CV editor's Preview tab.
 */
export function CvPreview({ cv, name }: { cv: CVStructure; name: string }) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const locale = dateLocale(i18n.lang);

  return (
    <View style={[styles.sheet, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <View style={styles.head}>
        <Text style={[styles.name, { color: theme.colors.primary }]}>{name}</Text>
        <Text style={[styles.summary, { color: theme.colors.textSecondary }]}>
          {cv.summary ? cv.summary : <Text style={[styles.empty, { color: theme.colors.textFaint }]}>{i18n.t('cvPreview.summaryEmpty')}</Text>}
        </Text>
      </View>

      {cv.skills.length > 0 ? (
        <Section title={i18n.t('cvPreview.skills')}>
          <View style={styles.skillsRow}>
            {cv.skills.map((skill) => (
              <View
                key={skill}
                style={[styles.skillChip, { borderColor: theme.colors.borderStrong }]}
              >
                <Text style={[styles.skillChipText, { color: theme.colors.textSecondary }]}>{skill}</Text>
              </View>
            ))}
          </View>
        </Section>
      ) : null}

      {cv.experience.length > 0 ? (
        <Section title={i18n.t('cvPreview.experience')}>
          {cv.experience.map((exp, index) => (
            <View key={index} style={styles.entry}>
              <View style={styles.entryHead}>
                <Text style={[styles.entryTitle, { color: theme.colors.text }]}>{exp.title}</Text>
                <Text style={[styles.dates, { color: theme.colors.textMuted }]}>
                  {formatDateRange(exp.start_date, exp.end_date, locale)}
                </Text>
              </View>
              <Text style={[styles.entrySub, { color: theme.colors.textSecondary }]}>{exp.company}</Text>
              {exp.bullets.length > 0 ? (
                <View style={styles.bullets}>
                  {exp.bullets.map((bullet, bulletIndex) => (
                    <Text key={bulletIndex} style={[styles.bullet, { color: theme.colors.text }]}>
                      •  {bullet}
                    </Text>
                  ))}
                </View>
              ) : null}
            </View>
          ))}
        </Section>
      ) : null}

      {cv.education.length > 0 ? (
        <Section title={i18n.t('cvPreview.education')}>
          {cv.education.map((edu, index) => (
            <View key={index} style={styles.entry}>
              <View style={styles.entryHead}>
                <Text style={[styles.entryTitle, { color: theme.colors.text }]}>{edu.degree}</Text>
                <Text style={[styles.dates, { color: theme.colors.textMuted }]}>{edu.year ?? ''}</Text>
              </View>
              <Text style={[styles.entrySub, { color: theme.colors.textSecondary }]}>{edu.institution}</Text>
            </View>
          ))}
        </Section>
      ) : null}

      {cv.projects.length > 0 ? (
        <Section title={i18n.t('cvPreview.projects')}>
          {cv.projects.map((project, index) => (
            <View key={index} style={styles.entry}>
              <View style={styles.entryHead}>
                <Text style={[styles.entryTitle, { color: theme.colors.text }]}>{project.name}</Text>
                {project.link ? <Text style={[styles.dates, { color: theme.colors.textMuted }]}>{project.link}</Text> : null}
              </View>
              {project.description ? (
                <Text style={[styles.projectDesc, { color: theme.colors.text }]}>{project.description}</Text>
              ) : null}
            </View>
          ))}
        </Section>
      ) : null}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const { theme } = useTheme();
  return (
    <View style={[styles.section, { borderTopColor: theme.colors.border }]}>
      <Text style={[styles.sectionTitle, { color: theme.colors.accent }]}>{title}</Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 24,
  },
  head: {
    marginBottom: 16,
  },
  name: {
    fontSize: 22,
    fontWeight: '700',
    marginBottom: 6,
    letterSpacing: 0.2,
  },
  summary: {
    fontSize: 14,
    lineHeight: 20,
  },
  empty: {
    fontStyle: 'italic',
  },
  section: {
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 10,
  },
  sectionBody: {
    gap: 12,
  },
  skillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  skillChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 9999,
    borderWidth: 1,
  },
  skillChipText: {
    fontSize: 12,
  },
  entry: {
    gap: 2,
  },
  entryHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 8,
  },
  entryTitle: {
    fontSize: 14,
    fontWeight: '700',
    flexShrink: 1,
  },
  entrySub: {
    fontSize: 13,
  },
  dates: {
    fontSize: 12,
  },
  bullets: {
    marginTop: 6,
    gap: 4,
  },
  bullet: {
    fontSize: 13,
    lineHeight: 19,
  },
  projectDesc: {
    fontSize: 13,
    lineHeight: 19,
    marginTop: 2,
  },
});
