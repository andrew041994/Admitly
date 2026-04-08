import Constants from 'expo-constants';

const extras = Constants.expoConfig?.extra ?? {};

export const env = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? (extras.apiBaseUrl as string) ?? 'http://192.168.1.20:8000',
  enableDevTestCheckout: (process.env.EXPO_PUBLIC_ENABLE_DEV_TEST_CHECKOUT ?? (extras.enableDevTestCheckout as string) ?? 'false') === 'true',
};
