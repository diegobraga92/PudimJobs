import * as DocumentPicker from 'expo-document-picker';
import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { exportPdf, parseCvFile } from '@/api/cv';
import { CvPreview } from '@/components/cv-preview/CvPreview';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { TextArea } from '@/components/ui/TextArea';
import { Icon } from '@/components/icons/Icon';
import { Skeleton } from '@/components/ui/Skeleton';
import { useConfirm } from '@/components/confirm/ConfirmProvider';
import { useToast } from '@/components/toast/ToastProvider';
import {
  useCvVersions,
  useDeleteCvVersion,
  useDeleteGeneratedCv,
  useGeneratedCvs,
  useSaveCv,
} from '@/hooks/useCv';
import { useI18n } from '@/i18n/I18nProvider';
import { useAuthStore } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';
import { CVStructure, ExperienceItem, GeneratedCV, MasterCV } from '@/types';
import { shortDate, dateLocale } from '@/utils/dates';
import { parseLines, parseList } from '@/utils/lists';
import { sharePdfBlob, sharePdfFromUrl } from '@/utils/pdf';

interface ExperienceForm {
  company: string;
  title: string;
  start_date: string;
  end_date: string;
  bulletsText: string;
}

interface EducationForm {
  institution: string;
  degree: string;
  year: string;
}

interface ProjectForm {
  name: string;
  description: string;
  link: string;
}

interface CvFormState {
  summary: string;
  skillsText: string;
  experience: ExperienceForm[];
  education: EducationForm[];
  projects: ProjectForm[];
}

const EMPTY_FORM: CvFormState = {
  summary: '',
  skillsText: '',
  experience: [],
  education: [],
  projects: [],
};

function fromStructure(cv: CVStructure): CvFormState {
  return {
    summary: cv.summary ?? '',
    skillsText: (cv.skills ?? []).join(', '),
    experience: (cv.experience ?? []).map((item) => ({
      company: item.company,
      title: item.title,
      start_date: item.start_date ?? '',
      end_date: item.end_date ?? '',
      bulletsText: (item.bullets ?? []).join('\n'),
    })),
    education: (cv.education ?? []).map((item) => ({
      institution: item.institution,
      degree: item.degree,
      year: item.year ?? '',
    })),
    projects: (cv.projects ?? []).map((item) => ({
      name: item.name,
      description: item.description ?? '',
      link: item.link ?? '',
    })),
  };
}

function toStructure(form: CvFormState): CVStructure {
  return {
    summary: form.summary ?? '',
    skills: parseList(form.skillsText ?? ''),
    experience: form.experience.map((item): ExperienceItem => ({
      company: item.company,
      title: item.title,
      start_date: item.start_date || null,
      end_date: item.end_date || null,
      bullets: parseLines(item.bulletsText),
    })),
    education: form.education.map((item) => ({
      institution: item.institution,
      degree: item.degree,
      year: item.year || null,
    })),
    projects: form.projects.map((item) => ({
      name: item.name,
      description: item.description || null,
      link: item.link || null,
    })),
  };
}

function displayNameFromEmail(email: string | undefined): string {
  if (!email) {
    return 'Your Name';
  }
  const local = email.split('@')[0] || '';
  return (
    local
      .split(/[._-]/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ') || 'Your Name'
  );
}


export function CvEditorScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const user = useAuthStore((state) => state.user);

  const { data: versions = [], isPending: versionsPending } = useCvVersions();
  const { data: generated = [] } = useGeneratedCvs();
  const saveCv = useSaveCv();
  const deleteVersion = useDeleteCvVersion();
  const deleteGenerated = useDeleteGeneratedCv();

  const [mode, setMode] = useState<'edit' | 'preview'>('edit');
  const [form, setForm] = useState<CvFormState>(EMPTY_FORM);
  const [loadedVersionId, setLoadedVersionId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const cvName = useMemo(() => displayNameFromEmail(user?.email), [user?.email]);
  const current = versions.find((version) => version.is_current);

  // Load the current version into the editor the first time it becomes
  // available (render-time adjustment, mirroring the web's ngOnInit reload).
  if (versions.length > 0 && current && current.id !== loadedVersionId) {
    setLoadedVersionId(current.id);
    setForm(fromStructure(current.structured_json));
  } else if (versions.length > 0 && !current && loadedVersionId === null) {
    setLoadedVersionId('__empty__');
    setForm(EMPTY_FORM);
  }

  const update = <K extends keyof CvFormState>(key: K, value: CvFormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const updateExperience = (index: number, key: keyof ExperienceForm, value: string) =>
    setForm((current) => ({
      ...current,
      experience: current.experience.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    }));

  const updateEducation = (index: number, key: keyof EducationForm, value: string) =>
    setForm((current) => ({
      ...current,
      education: current.education.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    }));

  const updateProject = (index: number, key: keyof ProjectForm, value: string) =>
    setForm((current) => ({
      ...current,
      projects: current.projects.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    }));

  const addExperience = () =>
    update('experience', [
      ...form.experience,
      { company: '', title: '', start_date: '', end_date: '', bulletsText: '' },
    ]);

  const addEducation = () =>
    update('education', [...form.education, { institution: '', degree: '', year: '' }]);

  const addProject = () =>
    update('projects', [...form.projects, { name: '', description: '', link: '' }]);

  const removeExperience = (index: number) =>
    update('experience', form.experience.filter((_, i) => i !== index));

  const removeEducation = (index: number) =>
    update('education', form.education.filter((_, i) => i !== index));

  const removeProject = (index: number) =>
    update('projects', form.projects.filter((_, i) => i !== index));



  const save = () => {
    setMessage(null);
    saveCv.mutate(
      { structured_json: toStructure(form) },
      {
        onSuccess: (saved) => {
          setLoadedVersionId(saved.id);
          setForm(fromStructure(saved.structured_json));
          setMessage(i18n.t('cv.savedAs', { label: saved.label }));
          toast.success(i18n.t('cv.savedAsToast', { label: saved.label }));
        },
        onError: () => {
          setError(i18n.t('errors.failedSaveCV'));
          toast.error(i18n.t('errors.failedSaveCV'));
        },
      },
    );
  };

  const importCv = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      ],
      copyToCacheDirectory: true,
    });
    if (result.canceled || result.assets.length === 0) {
      return;
    }
    const asset = result.assets[0];
    const ext = asset.name.split('.').pop()?.toLowerCase();
    if (ext !== 'pdf' && ext !== 'docx') {
      setError(i18n.t('errors.unsupportedCvFile'));
      toast.error(i18n.t('errors.unsupportedCvFile'));
      return;
    }
    setImporting(true);
    setMessage(null);
    try {
      const structure = await parseCvFile(asset.uri, asset.name);
      setForm(fromStructure(structure));
      setMessage(i18n.t('cv.imported'));
      toast.success(i18n.t('cv.importedToast'));
    } catch {
      setError(i18n.t('errors.failedParseCV'));
      toast.error(i18n.t('errors.failedParseCV'));
    } finally {
      setImporting(false);
    }
  };

  const exportPdfNow = async () => {
    if (exporting) {
      return;
    }
    setExporting(true);
    setMessage(null);
    try {
      const blob = await exportPdf(toStructure(form));
      await sharePdfBlob(blob, 'cv.pdf');
      toast.success(i18n.t('cv.pdfExported'));
    } catch {
      setError(i18n.t('errors.failedExportPdf'));
      toast.error(i18n.t('errors.failedExportPdf'));
    } finally {
      setExporting(false);
    }
  };

  const removeVersion = async (version: MasterCV) => {
    const confirmed = await confirm.confirm({
      title: i18n.t('cv.deleteVersionTitle'),
      message: i18n.t('cv.deleteVersionMessage', { label: version.label }),
      confirmLabel: i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteVersion.mutate(version.id, {
      onSuccess: () => {
        setMessage(i18n.t('cv.versionDeleted'));
        toast.success(i18n.t('cv.versionDeleted'));
        if (version.is_current) {
          setLoadedVersionId(null);
        }
      },
      onError: () => {
        setError(i18n.t('errors.failedDeleteCV'));
        toast.error(i18n.t('errors.failedDeleteCV'));
      },
    });
  };

  const masterCvVersion = (item: GeneratedCV): MasterCV | undefined =>
    item.master_cv_id ? versions.find((version) => version.id === item.master_cv_id) : undefined;

  const editGenerated = (item: GeneratedCV) => {
    const version = masterCvVersion(item);
    if (!version) {
      setError(i18n.t('errors.failedLoadCV'));
      return;
    }
    setForm(fromStructure(version.structured_json));
    setMode('edit');
    setMessage(i18n.t('cv.editingTailored', { job: item.job_title ?? '' }));
    toast.success(i18n.t('cv.editingTailoredToast', { job: item.job_title ?? '' }));
  };

  const downloadGenerated = (id: string) => {
    sharePdfFromUrl(`/api/cv/generated/${id}/pdf`, `tailored-cv-${id}.pdf`).catch(() => {
      setError(i18n.t('errors.failedDownloadPdf'));
      toast.error(i18n.t('errors.failedDownloadPdf'));
    });
  };

  const removeGenerated = async (item: GeneratedCV) => {
    const title = item.job_title ?? item.job_company ?? i18n.t('cv.tailoredCvs');
    const confirmed = await confirm.confirm({
      title: i18n.t('cv.deleteTailoredTitle'),
      message: i18n.t('cv.deleteTailoredMessage', { title }),
      confirmLabel: i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    deleteGenerated.mutate(item.id, {
      onSuccess: () => {
        setMessage(i18n.t('cv.tailoredDeleted'));
        toast.success(i18n.t('cv.tailoredDeleted'));
      },
      onError: () => {
        setError(i18n.t('errors.failedDeleteGeneratedCV'));
        toast.error(i18n.t('errors.failedDeleteGeneratedCV'));
      },
    });
  };

  return (
    <ScrollView style={[styles.container, { backgroundColor: theme.colors.bg }]} contentContainerStyle={styles.content}>
      <View style={styles.head}>
        <Text style={[styles.title, { color: theme.colors.text }]}>{i18n.t('cv.title')}</Text>
        <View style={styles.headActions}>
          <SegmentedControl
            value={mode}
            onChange={setMode}
            options={[
              { label: i18n.t('cv.edit'), value: 'edit' as const, icon: <Icon name="pencil" size={15} /> },
              { label: i18n.t('cv.preview'), value: 'preview' as const, icon: <Icon name="eye" size={15} /> },
            ]}
          />
          <View style={styles.headButtons}>
            <Button variant="ghost" size="sm" onPress={() => void importCv()} loading={importing} disabled={mode !== 'edit'}>
              {importing ? i18n.t('cv.importing') : i18n.t('cv.import')}
            </Button>
            <Button variant="ghost" size="sm" onPress={() => void exportPdfNow()} loading={exporting}>
              {exporting ? i18n.t('cv.exporting') : i18n.t('cv.exportPdf')}
            </Button>
            <Button size="sm" onPress={save} loading={saveCv.isPending} disabled={mode !== 'edit'}>
              {saveCv.isPending ? i18n.t('cv.saving') : i18n.t('cv.saveNewVersion')}
            </Button>
          </View>
        </View>
      </View>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {message ? <Alert tone="success">{message}</Alert> : null}

      {mode === 'edit' ? (
        <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.summary')}</Text>
          <FormField>
            <TextArea
              value={form.summary}
              onChangeText={(value) => update('summary', value)}
              placeholder={i18n.t('cv.summaryPlaceholder')}
              minHeight={80}
            />
          </FormField>

          <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.skills')}</Text>
          <FormField>
            <Input
              value={form.skillsText}
              onChangeText={(value) => update('skillsText', value)}
              placeholder={i18n.t('cv.skillsPlaceholder')}
            />
          </FormField>

          <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.experience')}</Text>
          {form.experience.map((item, index) => (
            <View key={index} style={[styles.subPanel, { borderColor: theme.colors.border }]}>
              <View style={styles.subHead}>
                <Text style={[styles.subTitle, { color: theme.colors.text }]}>
                  {i18n.t('cv.experienceItem', { n: index + 1 })}
                </Text>
                <Button variant="ghost" size="sm" onPress={() => removeExperience(index)}>
                  <Icon name="trash" size={13} />
                  {i18n.t('common.remove')}
                </Button>
              </View>
              <View style={styles.row}>
                <FormField label={i18n.t('common.company')} style={styles.rowField}>
                  <Input value={item.company} onChangeText={(value) => updateExperience(index, 'company', value)} />
                </FormField>
                <FormField label={i18n.t('common.title')} style={styles.rowField}>
                  <Input value={item.title} onChangeText={(value) => updateExperience(index, 'title', value)} />
                </FormField>
              </View>
              <View style={styles.row}>
                <FormField label={i18n.t('cv.start')} style={styles.rowField}>
                  <Input value={item.start_date} onChangeText={(value) => updateExperience(index, 'start_date', value)} placeholder="2020-01" />
                </FormField>
                <FormField label={i18n.t('cv.end')} style={styles.rowField}>
                  <Input value={item.end_date} onChangeText={(value) => updateExperience(index, 'end_date', value)} placeholder="2023-06" />
                </FormField>
              </View>
              <FormField label={i18n.t('cv.bullets')}>
                <TextArea
                  value={item.bulletsText}
                  onChangeText={(value) => updateExperience(index, 'bulletsText', value)}
                  placeholder="Built async pipelines"
                  minHeight={64}
                />
              </FormField>
            </View>
          ))}
          <Button variant="ghost" size="sm" onPress={addExperience}>
            <Icon name="plus" size={15} />
            {i18n.t('cv.addExperience')}
          </Button>



          <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.education')}</Text>
          {form.education.map((item, index) => (
            <View key={index} style={[styles.subPanel, { borderColor: theme.colors.border }]}>
              <View style={styles.subHead}>
                <Text style={[styles.subTitle, { color: theme.colors.text }]}>
                  {i18n.t('cv.educationItem', { n: index + 1 })}
                </Text>
                <Button variant="ghost" size="sm" onPress={() => removeEducation(index)}>
                  <Icon name="trash" size={13} />
                  {i18n.t('common.remove')}
                </Button>
              </View>
              <FormField label={i18n.t('cv.institution')}>
                <Input value={item.institution} onChangeText={(value) => updateEducation(index, 'institution', value)} />
              </FormField>
              <View style={styles.row}>
                <FormField label={i18n.t('cv.degree')} style={styles.rowField}>
                  <Input value={item.degree} onChangeText={(value) => updateEducation(index, 'degree', value)} />
                </FormField>
                <FormField label={i18n.t('cv.year')} style={styles.rowField}>
                  <Input value={item.year} onChangeText={(value) => updateEducation(index, 'year', value)} />
                </FormField>
              </View>
            </View>
          ))}
          <Button variant="ghost" size="sm" onPress={addEducation}>
            <Icon name="plus" size={15} />
            {i18n.t('cv.addEducation')}
          </Button>

          <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.projects')}</Text>
          {form.projects.map((item, index) => (
            <View key={index} style={[styles.subPanel, { borderColor: theme.colors.border }]}>
              <View style={styles.subHead}>
                <Text style={[styles.subTitle, { color: theme.colors.text }]}>
                  {i18n.t('cv.projectItem', { n: index + 1 })}
                </Text>
                <Button variant="ghost" size="sm" onPress={() => removeProject(index)}>
                  <Icon name="trash" size={13} />
                  {i18n.t('common.remove')}
                </Button>
              </View>
              <FormField label={i18n.t('common.name')}>
                <Input value={item.name} onChangeText={(value) => updateProject(index, 'name', value)} />
              </FormField>
              <FormField label={i18n.t('cv.link')}>
                <Input value={item.link} onChangeText={(value) => updateProject(index, 'link', value)} autoCapitalize="none" />
              </FormField>
              <FormField label={i18n.t('common.description')}>
                <TextArea
                  value={item.description}
                  onChangeText={(value) => updateProject(index, 'description', value)}
                  minHeight={56}
                />
              </FormField>
            </View>
          ))}
          <Button variant="ghost" size="sm" onPress={addProject}>
            <Icon name="plus" size={15} />
            {i18n.t('cv.addProject')}
          </Button>
        </View>
      ) : (
        <CvPreview cv={toStructure(form)} name={cvName} />
      )}

      <View style={[styles.panel, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
        <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.versionHistory')}</Text>
        {versionsPending ? (
          <View style={styles.historySkeleton}>
            <Skeleton width="60%" height={14} />
            <Skeleton width="40%" height={12} style={{ marginTop: 6 }} />
          </View>
        ) : versions.length === 0 ? (
          <Text style={[styles.muted, { color: theme.colors.textMuted }]}>{i18n.t('cv.noVersions')}</Text>
        ) : (
          versions.map((version) => (
            <View key={version.id} style={[styles.historyRow, { borderTopColor: theme.colors.border }]}>
              <View style={styles.historyInfo}>
                <View style={styles.historyLabelRow}>
                  <Text style={[styles.historyLabel, { color: version.is_current ? theme.colors.primary : theme.colors.text }]}>
                    {version.label}
                  </Text>
                  {version.is_current ? <Badge variant="info">{i18n.t('cv.current')}</Badge> : null}
                </View>
                <Text style={[styles.historyDate, { color: theme.colors.textMuted }]}>{shortDate(version.updated_at, dateLocale(i18n.lang))}</Text>
              </View>
              <Button variant="ghost" size="sm" onPress={() => void removeVersion(version)}>
                <Icon name="trash" size={14} />
              </Button>
            </View>
          ))
        )}

        <Text style={[styles.sectionTitle, { color: theme.colors.text }]}>{i18n.t('cv.tailoredCvs')}</Text>
        {generated.length === 0 ? (
          <Text style={[styles.muted, { color: theme.colors.textMuted }]}>{i18n.t('cv.noTailored')}</Text>
        ) : (
          generated.map((item) => (
            <View key={item.id} style={[styles.generatedRow, { borderTopColor: theme.colors.border }]}>
              <View style={styles.generatedInfo}>
                <Text style={[styles.generatedTitle, { color: theme.colors.text }]}>{item.job_title ?? '—'}</Text>
                <Text style={[styles.muted, { color: theme.colors.textMuted }]}>{item.job_company ?? ''}</Text>
              </View>
              <View style={styles.generatedActions}>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!masterCvVersion(item)}
                  onPress={() => editGenerated(item)}
                >
                  {i18n.t('cv.edit')}
                </Button>
                <Button variant="ghost" size="sm" onPress={() => downloadGenerated(item.id)}>
                  <Icon name="download" size={14} />
                  {i18n.t('cv.pdf')}
                </Button>
                <Button variant="ghost" size="sm" onPress={() => void removeGenerated(item)}>
                  <Icon name="trash" size={14} />
                </Button>
              </View>
            </View>
          ))
        )}
      </View>
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
    gap: 12,
  },
  head: {
    gap: 10,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  headActions: {
    gap: 10,
  },
  headButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  panel: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    gap: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginTop: 4,
  },
  subPanel: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    gap: 10,
  },
  subHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  subTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowField: {
    flex: 1,
  },
  muted: {
    fontSize: 13,
  },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
  },
  historySkeleton: {
    gap: 4,
  },
  historyInfo: {
    flex: 1,
    gap: 2,
  },
  historyLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  historyLabel: {
    fontSize: 14,
    fontWeight: '600',
  },
  historyDate: {
    fontSize: 12,
  },
  generatedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
    borderTopWidth: 1,
  },
  generatedInfo: {
    flex: 1,
  },
  generatedTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  generatedActions: {
    flexDirection: 'row',
    gap: 4,
  },
});

