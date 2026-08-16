import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { Icon } from '@/components/icons/Icon';
import { useI18n } from '@/i18n/I18nProvider';
import { useTheme } from '@/theme/ThemeProvider';

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Renders the confirm button in destructive red. */
  destructive?: boolean;
}

interface ConfirmContextValue {
  /** Opens a confirmation dialog and resolves when the user confirms/cancels. */
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

/**
 * Promise-based confirmation dialog — the React Native analog of the web
 * ConfirmService (which replaces `window.confirm`).
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { theme } = useTheme();
  const i18n = useI18n();
  const [visible, setVisible] = useState(false);
  const [options, setOptions] = useState<Required<ConfirmOptions> | null>(null);
  const resolveRef = useRef<((confirmed: boolean) => void) | null>(null);

  const confirm = useCallback(
    (opts: ConfirmOptions) => {
      setOptions({
        title: opts.title ?? i18n.t('confirm.areYouSure'),
        message: opts.message,
        confirmLabel: opts.confirmLabel ?? i18n.t('confirm.confirm'),
        cancelLabel: opts.cancelLabel ?? i18n.t('confirm.cancel'),
        destructive: opts.destructive ?? false,
      });
      setVisible(true);
      return new Promise<boolean>((resolve) => {
        resolveRef.current = resolve;
      });
    },
    [i18n],
  );

  const close = useCallback((confirmed: boolean) => {
    setVisible(false);
    resolveRef.current?.(confirmed);
    resolveRef.current = null;
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <Modal visible={visible} transparent animationType="fade" onRequestClose={() => close(false)}>
        <Pressable style={styles.backdrop} onPress={() => close(false)}>
          <Pressable
            style={[
              styles.dialog,
              { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
            ]}
            onPress={() => undefined}
          >
            <View style={styles.dialogHead}>
              <View
                style={[
                  styles.iconWrap,
                  {
                    backgroundColor: options?.destructive
                      ? theme.colors.dangerSoft
                      : theme.colors.warningSoft,
                  },
                ]}
              >
                <Icon
                  name="triangle-alert"
                  size={24}
                  color={options?.destructive ? theme.colors.danger : theme.colors.warning}
                />
              </View>
              <View style={styles.body}>
                <Text style={[styles.title, { color: theme.colors.text }]}>{options?.title}</Text>
                <Text style={[styles.message, { color: theme.colors.textMuted }]}>
                  {options?.message}
                </Text>
              </View>
            </View>
            <View style={styles.actions}>
              <Pressable
                onPress={() => close(false)}
                style={styles.cancelBtn}
                accessibilityRole="button"
              >
                <Text style={[styles.cancelText, { color: theme.colors.text }]}>
                  {options?.cancelLabel}
                </Text>
              </Pressable>
              <Pressable
                onPress={() => close(true)}
                accessibilityRole="button"
                style={[
                  styles.confirmBtn,
                  {
                    backgroundColor: options?.destructive
                      ? theme.colors.danger
                      : theme.colors.primary,
                  },
                ]}
              >
                <Text style={[styles.confirmText, { color: theme.colors.onPrimary }]}>
                  {options?.confirmLabel}
                </Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmContextValue {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error('useConfirm must be used within <ConfirmProvider>');
  }
  return ctx;
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.5)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  dialog: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 20,
    maxWidth: 420,
    width: '100%',
  },
  dialogHead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: 9999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  message: {
    fontSize: 14,
    lineHeight: 20,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 14,
  },
  cancelBtn: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
  },
  cancelText: {
    fontSize: 14,
    fontWeight: '600',
  },
  confirmBtn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  confirmText: {
    fontSize: 14,
    fontWeight: '600',
  },
});
