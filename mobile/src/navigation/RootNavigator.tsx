import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useSession } from '../context/SessionContext';
import { theme } from '../theme';
import { AppStackParamList, AuthStackParamList } from './types';
import { BootScreen } from './screens/BootScreen';
import { HomeScreen } from './screens/HomeScreen';
import { PlaceholderScreen } from './screens/PlaceholderScreen';
import { SignInScreen } from './screens/SignInScreen';
import { SignUpScreen } from './screens/SignUpScreen';
import { WelcomeScreen } from './screens/WelcomeScreen';

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const AppStack = createNativeStackNavigator<AppStackParamList>();

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: theme.colors.background,
    card: theme.colors.surface,
    text: theme.colors.textPrimary,
    border: theme.colors.border,
    primary: theme.colors.primary,
  },
};

function AuthNavigator() {
  const { signInPlaceholder } = useSession();

  return (
    <AuthStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.primary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      <AuthStack.Screen name="Welcome" options={{ headerShown: false }}>
        {({ navigation }) => (
          <WelcomeScreen
            onGetStarted={() => navigation.navigate('SignIn')}
            onCreateAccount={() => navigation.navigate('SignUp')}
          />
        )}
      </AuthStack.Screen>
      <AuthStack.Screen name="SignIn">
        {() => <SignInScreen onContinue={signInPlaceholder} />}
      </AuthStack.Screen>
      <AuthStack.Screen name="SignUp" component={SignUpScreen} />
    </AuthStack.Navigator>
  );
}

function SignedInNavigator() {
  const { signOut } = useSession();

  return (
    <AppStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.primary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      <AppStack.Screen name="Home">
        {({ navigation }) => (
          <HomeScreen onOpenProfile={() => navigation.navigate('Profile')} onSignOut={signOut} />
        )}
      </AppStack.Screen>
      <AppStack.Screen
        name="EventDetail"
        children={() => <PlaceholderScreen title="Event detail" description="Event detail foundation route only." />}
      />
      <AppStack.Screen
        name="MyTickets"
        children={() => <PlaceholderScreen title="My tickets" description="Ticket wallet UI is out of scope in Phase 1." />}
      />
      <AppStack.Screen
        name="Profile"
        children={() => <PlaceholderScreen title="Profile" description="Account profile shell for future phases." />}
      />
    </AppStack.Navigator>
  );
}

export function RootNavigator() {
  const { state } = useSession();

  return (
    <NavigationContainer theme={navTheme}>
      {state === 'booting' ? <BootScreen /> : state === 'signedOut' ? <AuthNavigator /> : <SignedInNavigator />}
    </NavigationContainer>
  );
}
