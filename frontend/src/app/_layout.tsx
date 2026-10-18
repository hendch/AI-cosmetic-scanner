import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { Colors } from '@/constants/theme';
import { ScanProvider } from '@/scan/scan-context';

export default function RootLayout() {
  // One light design everywhere (see hooks/use-theme.ts).
  const navTheme = { ...DefaultTheme, colors: { ...DefaultTheme.colors, background: Colors.light.background, primary: Colors.light.accent } };

  return (
    <ThemeProvider value={navTheme}>
      <ScanProvider>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false }} />
      </ScanProvider>
    </ThemeProvider>
  );
}
