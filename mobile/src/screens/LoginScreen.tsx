import { zodResolver } from '@hookform/resolvers/zod';
import { useCallback, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { z } from 'zod';

import { apiClient } from '@/api/client';
import { login } from '@/api/auth';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Input } from '@/components/ui/Input';
import { Icon } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useAuthStore } from '@/store/auth';
import { useTheme } from '@/theme/ThemeProvider';
import { User } from '@/types';

const loginSchema = z.object({
  email: z.string().min(1).email(),
  password: z.string().min(6),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginScreen() {
  const { theme } = useTheme();
  const i18n = useI18n();
  const setSession = useAuthStore((state) => state.setSession);

  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = useCallback(
    async (values: LoginForm) => {
      if (loading) {
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const response = await login(values.email, values.password);
        setSession(response.access_token);
        // Warm the user profile cache immediately (mirrors adminGuard's auth.me()).
        try {
          const { data } = await apiClient.get<User>('/api/auth/me');
          setSession(response.access_token, data);
        } catch {
          // Profile refresh is best-effort; the drawer loads it lazily.
        }
      } catch {
        setError(i18n.t('login.invalidCredentials'));
        setLoading(false);
      }
    },
    [i18n, loading, setSession],
  );

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.colors.bg }]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.brand}>
            <View style={[styles.brandMark, { backgroundColor: theme.colors.primary }]}>
              <Icon name="briefcase" size={26} color={theme.colors.onPrimary} />
            </View>
            <Text style={[styles.brandName, { color: theme.colors.text }]}>PudimJobs</Text>
            <Text style={[styles.tagline, { color: theme.colors.textMuted }]}>
              {i18n.t('login.tagline')}
            </Text>
          </View>

          <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
            <FormField label={i18n.t('login.email')}>
              <Controller
                control={control}
                name="email"
                render={({ field }) => (
                  <Input
                    value={field.value}
                    onChangeText={field.onChange}
                    onBlur={field.onBlur}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoComplete="email"
                    placeholder="you@example.com"
                    accessibilityLabel={i18n.t('login.email')}
                  />
                )}
              />
              {submitted && errors.email ? (
                <Text style={[styles.fieldError, { color: theme.colors.danger }]}>
                  {errors.email.type === 'invalid_email' || errors.email.message === 'Invalid email'
                    ? i18n.t('login.emailInvalid')
                    : i18n.t('login.emailRequired')}
                </Text>
              ) : null}
            </FormField>

            <FormField label={i18n.t('login.password')}>
              <Controller
                control={control}
                name="password"
                render={({ field }) => (
                  <Input
                    value={field.value}
                    onChangeText={field.onChange}
                    onBlur={field.onBlur}
                    passwordToggle
                    showPassword={showPassword}
                    onTogglePassword={() => setShowPassword((current) => !current)}
                    autoCapitalize="none"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    accessibilityLabel={i18n.t('login.password')}
                  />
                )}
              />
              {submitted && errors.password ? (
                <Text style={[styles.fieldError, { color: theme.colors.danger }]}>
                  {errors.password.type === 'too_small'
                    ? i18n.t('login.passwordMinLength')
                    : i18n.t('login.passwordRequired')}
                </Text>
              ) : null}
            </FormField>

            {error ? (
              <Alert tone="error">
                <Text>{error}</Text>
              </Alert>
            ) : null}

            <Button
              onPress={() => {
                setSubmitted(true);
                void handleSubmit(onSubmit)();
              }}
              loading={loading}
              fullWidth
              accessibilityLabel={i18n.t('login.signIn')}
            >
              {loading ? i18n.t('login.signingIn') : i18n.t('login.signIn')}
            </Button>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
    gap: 24,
  },
  brand: {
    alignItems: 'center',
    gap: 8,
  },
  brandMark: {
    width: 56,
    height: 56,
    borderRadius: 9999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandName: {
    fontSize: 24,
    fontWeight: '700',
  },
  tagline: {
    fontSize: 14,
    textAlign: 'center',
  },
  card: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 20,
  },
  fieldError: {
    fontSize: 12,
    marginTop: 4,
  },
});

