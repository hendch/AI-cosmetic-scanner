import '@/global.css';

import { Platform } from 'react-native';

// Cool mineral neutrals with one cobalt accent. The four status tones (clear, attention,
// prohibited, unknown) each have a soft tint for pills and tiles. Cobalt is never a status colour.
export const Colors = {
  light: {
    background: '#F2F4F3',
    surface: '#FFFFFF',
    surfaceAlt: '#E9EDEB',
    text: '#121816',
    textSecondary: '#56635F',
    line: '#DCE2DF',
    accent: '#2346D6',
    accentSoft: '#E7ECFF',
    onAccent: '#FFFFFF',
    ink: '#121816',
    onInk: '#FFFFFF',
    clear: '#1F7A4D',
    attention: '#9A5800',
    prohibited: '#B8322A',
    unknown: '#5A6774',
    clearSoft: '#E3F2EA',
    attentionSoft: '#FBEFD9',
    prohibitedSoft: '#FBE5E2',
    unknownSoft: '#ECEFF2',
  },
  dark: {
    background: '#0F1413',
    surface: '#182120',
    surfaceAlt: '#212C2A',
    text: '#E7EEEC',
    textSecondary: '#9AA9A5',
    line: '#2A3634',
    accent: '#8BA2FF',
    accentSoft: '#1E2752',
    onAccent: '#0B1022',
    ink: '#E7EEEC',
    onInk: '#0F1413',
    clear: '#6FCB98',
    attention: '#F0B060',
    prohibited: '#F2877C',
    unknown: '#A3B0BD',
    clearSoft: '#163126',
    attentionSoft: '#3A2A10',
    prohibitedSoft: '#3D1C19',
    unknownSoft: '#222B33',
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
  display: { fontSize: 34, lineHeight: 39, fontWeight: '700', letterSpacing: -0.8 },
  title: { fontSize: 26, lineHeight: 31, fontWeight: '700', letterSpacing: -0.4 },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  strong: { fontSize: 16, lineHeight: 24, fontWeight: '600' },
  small: { fontSize: 14, lineHeight: 20, fontWeight: '400' },
  caption: { fontSize: 12, lineHeight: 16, fontWeight: '500' },
  // The ingredient list as printed on the back of a bottle.
  inci: { fontSize: 15, lineHeight: 26, fontWeight: '600', letterSpacing: 0.4 },
} as const;

export const Spacing = { one: 4, two: 8, three: 12, four: 16, five: 24, six: 32, seven: 48 } as const;

export const MaxContentWidth = 680;
