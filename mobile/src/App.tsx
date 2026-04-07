import { StatusBar } from 'expo-status-bar';

import { SessionProvider } from './context/SessionContext';
import { RootNavigator } from './navigation/RootNavigator';

export default function App() {
  return (
    <SessionProvider>
      <StatusBar style="light" />
      <RootNavigator />
    </SessionProvider>
  );
}
