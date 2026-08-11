import Constants from 'expo-constants';

const extras = Constants.expoConfig?.extra ?? {};
const applicationVersion = Constants.expoConfig?.version ?? '0.0.0';
const configuredNativeBuild =
  Constants.expoConfig?.ios?.buildNumber
  ?? (Constants.expoConfig?.android?.versionCode != null
    ? String(Constants.expoConfig.android.versionCode)
    : '');
const runtimeIdentifier = Constants.expoRuntimeVersion ?? '';
const explicitSentryRelease =
  process.env.EXPO_PUBLIC_SENTRY_RELEASE
  ?? (extras.sentryRelease as string | undefined)
  ?? '';
const explicitSentryDist =
  process.env.EXPO_PUBLIC_SENTRY_DIST
  ?? (extras.sentryDist as string | undefined)
  ?? '';

export const env = {
  apiBaseUrl:
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  (extras.apiBaseUrl as string) ??
  'https://admitly.onrender.com',
  sentryDsn: process.env.EXPO_PUBLIC_SENTRY_DSN ?? (extras.sentryDsn as string) ?? '',
  sentryEnvironment:
    process.env.EXPO_PUBLIC_SENTRY_ENVIRONMENT
    ?? (extras.sentryEnvironment as string | undefined)
    ?? (__DEV__ ? 'development' : 'production'),
  sentryRelease: explicitSentryRelease.trim() || `com.admitly.app@${applicationVersion}`,
  sentryDist: explicitSentryDist.trim() || configuredNativeBuild || runtimeIdentifier,
};
