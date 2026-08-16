import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, IconName } from '@/components/icons/Icon';
import { useTheme } from '@/theme/ThemeProvider';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  warning: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DURATIONS: Record<ToastType, number> = {
  success: 3200,
  error: 5000,
  warning: 4200,
  info: 4200,
};

const TONE_ICON: Record<ToastType, IconName> = {
  success: 'circle-check',
  error: 'circle-alert',
  warning: 'triangle-alert',
  info: 'info',
};

const TONE_COLOR: Record<ToastType, string> = {
  success: 'success',
  error: 'danger',
  warning: 'warning',
  info: 'info',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (type: ToastType, message: string, duration?: number) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, type, message }]);
      setTimeout(() => dismiss(id), duration ?? DURATIONS[type]);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      success: (message, duration) => show('success', message, duration),
      error: (message, duration) => show('error', message, duration),
      warning: (message, duration) => show('warning', message, duration),
      info: (message, duration) => show('info', message, duration),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <View pointerEvents="box-none" style={[styles.viewport, { top: insets.top + 12 }]}>
        {toasts.map((toast) => (
          <View
            key={toast.id}
            style={[
              styles.toast,
              { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
            ]}
          >
            <Icon
              name={TONE_ICON[toast.type]}
              size={18}
              color={theme.colors[TONE_COLOR[toast.type] as 'success']}
            />
            <Text style={[styles.message, { color: theme.colors.text }]}>{toast.message}</Text>
            <Pressable onPress={() => dismiss(toast.id)} hitSlop={8} accessibilityRole="button">
              <Icon name="x" size={16} color={theme.colors.textFaint} />
            </Pressable>
          </View>
        ))}
      </View>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within <ToastProvider>');
  }
  return ctx;
}

const styles = StyleSheet.create({
  viewport: {
    position: 'absolute',
    right: 16,
    left: 16,
    zIndex: 1000,
    gap: 8,
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1,
    elevation: 8,
    shadowColor: '#0f172a',
    shadowOpacity: 0.2,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
  },
  message: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
});
