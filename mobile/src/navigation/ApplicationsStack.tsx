import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useI18n } from '@/i18n/I18nProvider';
import { ApplicationDetailScreen } from '@/screens/ApplicationDetailScreen';
import { ApplicationsScreen } from '@/screens/ApplicationsScreen';
import { TailoredCvEditorScreen } from '@/screens/TailoredCvEditorScreen';
import { useTheme } from '@/theme/ThemeProvider';
import { ApplicationsStackParamList } from './types';

const Stack = createNativeStackNavigator<ApplicationsStackParamList>();

/** Nested stack for Applications → application workspace (`/applications/:id`). */
export function ApplicationsStack() {
  const { theme } = useTheme();
  const i18n = useI18n();
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: theme.colors.bg },
      }}
    >
      <Stack.Screen
        name="ApplicationList"
        component={ApplicationsScreen}
        options={{ title: i18n.t('applications.title') }}
      />
      <Stack.Screen
        name="ApplicationDetail"
        component={ApplicationDetailScreen}
        options={{ title: i18n.t('applications.workspace') }}
      />
      <Stack.Screen
        name="TailoredCvEditor"
        component={TailoredCvEditorScreen}
        options={{ title: i18n.t('cv.panel.edit') }}
      />
    </Stack.Navigator>
  );
}
