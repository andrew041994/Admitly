import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useSession } from '../context/SessionContext';
import { theme } from '../theme';
import { AppStackParamList, AuthStackParamList } from './types';
import { BootScreen } from './screens/BootScreen';
import { ForgotPasswordScreen } from './screens/ForgotPasswordScreen';
import { HomeScreen } from './screens/HomeScreen';
import { PlaceholderScreen } from './screens/PlaceholderScreen';
import { ResetPasswordScreen } from './screens/ResetPasswordScreen';
import { SignInScreen } from './screens/SignInScreen';
import { SignUpScreen } from './screens/SignUpScreen';

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
  return (
    <AuthStack.Navigator
      initialRouteName="SignIn"
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.primary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      <AuthStack.Screen name="SignIn" options={{ headerShown: false }}>
        {({ navigation }) => (
          <SignInScreen
            onGoToSignUp={() => navigation.navigate('SignUp')}
            onGoToForgotPassword={() => navigation.navigate('ForgotPassword')}
          />
        )}
      </AuthStack.Screen>
      <AuthStack.Screen name="SignUp" options={{ headerShown: false }}>
        {({ navigation }) => <SignUpScreen onGoToSignIn={() => navigation.navigate('SignIn')} />}
      </AuthStack.Screen>
      <AuthStack.Screen name="ForgotPassword" options={{ headerShown: false }}>
        {({ navigation }) => (
          <ForgotPasswordScreen
            onGoToSignIn={() => navigation.navigate('SignIn')}
            onGoToResetPassword={() => navigation.navigate('ResetPassword')}
          />
        )}
      </AuthStack.Screen>
      <AuthStack.Screen name="ResetPassword" options={{ headerShown: false }}>
        {({ navigation }) => <ResetPasswordScreen onGoToSignIn={() => navigation.navigate('SignIn')} />}
      </AuthStack.Screen>
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
        children={() => (
          <PlaceholderScreen title="Event detail" description="Event detail foundation route only." />
        )}
      />
      <AppStack.Screen
        name="MyTickets"
        children={() => (
          <PlaceholderScreen title="My tickets" description="Ticket wallet UI is out of scope in Phase 1." />
        )}
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
