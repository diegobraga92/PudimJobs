import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useI18n } from '@/i18n/I18nProvider';
import { JobDetailScreen } from '@/screens/JobDetailScreen';
import { JobsScreen } from '@/screens/JobsScreen';
import { useTheme } from '@/theme/ThemeProvider';
import { JobsStackParamList } from './types';

const Stack = createNativeStackNavigator<JobsStackParamList>();

/** Nested stack for Jobs → Job detail (mirrors `/jobs` + `/jobs/:id`). */
export function JobsStack() {
  const { theme } = useTheme();
  const i18n = useI18n();
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: theme.colors.bg },
      }}
    >
      <Stack.Screen name="JobList" component={JobsScreen} options={{ title: i18n.t('jobs.title') }} />
      <Stack.Screen
        name="JobDetail"
        component={JobDetailScreen}
        options={{ title: i18n.t('jobDetail.backToJobs') }}
      />
    </Stack.Navigator>
  );
}
