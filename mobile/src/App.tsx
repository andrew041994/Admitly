import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Sentry from '@sentry/react-native';

import { SessionProvider } from './context/SessionContext';
import { RootNavigator } from './navigation/RootNavigator';
import { env } from './config/env';

if (env.sentryDsn) {
  Sentry.init({
    dsn: env.sentryDsn,
    environment: env.sentryEnvironment,
    release: env.sentryRelease,
    dist: env.sentryDist || undefined,
    sendDefaultPii: false,
  });
}

function App() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="light" />
        <RootNavigator />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

export default Sentry.wrap(App);
