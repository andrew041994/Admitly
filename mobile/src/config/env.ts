import Constants from 'expo-constants';

const extras = Constants.expoConfig?.extra ?? {};

export const env = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? (extras.apiBaseUrl as string) ?? 'http://192.168.1.123:8000',
};
