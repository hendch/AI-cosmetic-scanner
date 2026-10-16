import '@/global.css';

import { Platform } from 'react-native';

// Cool, mineral palette taken from frosted cosmetic packaging, with four
// status tones used everywhere an ingredient's state is shown.
export const Colors = {
  light: {
    background: '#EDF1EF',
    surface: '#F8FAF9',
    text: '#1B2B2A',
    textSecondary: '#566463',
    line: '#CBD5D2',
    accent: '#0E5D59',
    onAccent: '#FFFFFF',
    clear: '#2F6B4F',
    attention: '#9A5806',
    prohibited: '#B42318',
    unknown: '#5B6B7A',
  },
  dark: {
    background: '#141C1C',
    surface: '#1C2626',
    text: '#E4ECEA',
    textSecondary: '#9DADAA',
    line: '#2F3D3C',
    accent: '#5FB3AC',
    onAccent: '#0B1F1E',
    clear: '#6FBF97',
    attention: '#E0A050',
    prohibited: '#F07B6F',
    unknown: '#9AAABB',
  },
} as const;

export type Theme = (typeof Colors)['light' | 'dark'];
export type Tone = 'clear' | 'attention' | 'prohibited' | 'unknown';

export const Fonts = Platform.select({
  ios: { sans: 'system-ui', mono: 'ui-monospace' },
  web: { sans: 'var(--font-display)', mono: 'var(--font-mono)' },
  default: { sans: 'normal', mono: 'monospace' },
});

export const Type = {
  title: { fontSize: 28, lineHeight: 34, fontWeight: '700' },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  strong: { fontSize: 16, lineHeight: 24, fontWeight: '600' },
  small: { fontSize: 14, lineHeight: 20, fontWeight: '400' },
  // The ingredient list as printed on the back of a bottle.
  inci: { fontSize: 15, lineHeight: 26, fontWeight: '600', letterSpacing: 0.4 },
} as const;

export const Spacing = { one: 4, two: 8, three: 12, four: 16, five: 24, six: 32, seven: 48 } as const;

export const MaxContentWidth = 680;
