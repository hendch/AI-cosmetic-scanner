import { Colors } from '@/constants/theme';

// The app uses one light design on every device (the approved sketch), whatever the system setting.
// Colors.dark is kept for a future dark design.
export function useTheme() {
  return Colors.light;
}
