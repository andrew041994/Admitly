import Constants from 'expo-constants';

const extras = Constants.expoConfig?.extra ?? {};

export const env = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? (extras.apiBaseUrl as string) ?? 'https://admitly.onrender.com',
  enableDevTestCheckout: (process.env.EXPO_PUBLIC_ENABLE_DEV_TEST_CHECKOUT ?? (extras.enableDevTestCheckout as string) ?? 'false') === 'true',
};
