import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Icon, IconName } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { AuditTab } from './admin/AuditTab';
import { DlqTab } from './admin/DlqTab';
import { LlmTab } from './admin/LlmTab';
import { OverviewTab } from './admin/OverviewTab';
import { QualityTab } from './admin/QualityTab';
import { SourcesTab } from './admin/SourcesTab';

type AdminTabId = 'overview' | 'sources' | 'quality' | 'dlq' | 'audit' | 'llm';

interface TabDef {
  id: AdminTabId;
  labelKey: string;
  icon: IconName;
}

const TABS: TabDef[] = [
  { id: 'overview', labelKey: 'admin.tabs.overview', icon: 'layout-dashboard' },
  { id: 'sources', labelKey: 'admin.tabs.sources', icon: 'globe' },
  { id: 'quality', labelKey: 'admin.tabs.quality', icon: 'chart' },
  { id: 'dlq', labelKey: 'admin.tabs.dlq', icon: 'circle-alert' },
  { id: 'audit', labelKey: 'admin.tabs.audit', icon: 'history' },
  { id: 'llm', labelKey: 'admin.tabs.llm', icon: 'sparkle' },
];

/** Admin panel — mirrors the web 6-tab admin page. */
export function AdminScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const [activeTab, setActiveTab] = useState<AdminTabId>('overview');

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={[styles.tabBar, { borderBottomColor: theme.colors.border }]}
        contentContainerStyle={styles.tabBarContent}
      >
        {TABS.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <TabButton
              key={tab.id}
              label={i18n.t(tab.labelKey)}
              icon={tab.icon}
              active={active}
              onPress={() => setActiveTab(tab.id)}
            />
          );
        })}
      </ScrollView>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
        <Text style={[styles.pageTitle, { color: theme.colors.text }]}>
          {i18n.t('admin.title')}
        </Text>
        {activeTab === 'overview' ? <OverviewTab /> : null}
        {activeTab === 'sources' ? <SourcesTab /> : null}
        {activeTab === 'quality' ? <QualityTab /> : null}
        {activeTab === 'dlq' ? <DlqTab /> : null}
        {activeTab === 'audit' ? <AuditTab /> : null}
        {activeTab === 'llm' ? <LlmTab /> : null}
      </ScrollView>
    </View>
  );
}

function TabButton({
  label,
  icon,
  active,
  onPress,
}: {
  label: string;
  icon: IconName;
  active: boolean;
  onPress: () => void;
}) {
  const { theme } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      style={[
        styles.tab,
        active
          ? { backgroundColor: theme.colors.primarySoft, borderColor: theme.colors.primary }
          : { backgroundColor: 'transparent', borderColor: 'transparent' },
      ]}
    >
      <Icon name={icon} size={15} color={active ? theme.colors.primary : theme.colors.textMuted} />
      <Text
        style={[styles.tabLabel, { color: active ? theme.colors.primary : theme.colors.textMuted }]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  tabBar: {
    flexGrow: 0,
    borderBottomWidth: 1,
  },
  tabBarContent: {
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  tabLabel: {
    fontSize: 13,
    fontWeight: '600',
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    padding: 16,
    paddingBottom: 32,
  },
  pageTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 12,
  },
});
