import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useSession } from '../context/SessionContext';
import { theme } from '../theme';
import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { EventDiscoveryDetail, getDiscoverableEventDetail } from '../api/events';
import { AppStackParamList, AuthStackParamList } from './types';
import { BootScreen } from './screens/BootScreen';
import { EventDetailScreen } from './screens/EventDetailScreen';
import { ForgotPasswordScreen } from './screens/ForgotPasswordScreen';
import { HomeScreen } from './screens/HomeScreen';
import { PlaceholderScreen } from './screens/PlaceholderScreen';
import { ResetPasswordScreen } from './screens/ResetPasswordScreen';
import { SignInScreen } from './screens/SignInScreen';
import { SignUpScreen } from './screens/SignUpScreen';
import { PurchaseResultScreen } from './screens/PurchaseResultScreen';
import { MmgAgentCheckoutScreen } from './screens/MmgAgentCheckoutScreen';
import { CheckoutMethodScreen } from './screens/CheckoutMethodScreen';
import { TicketSelectionScreen } from './screens/TicketSelectionScreen';

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

function TicketSelectionRoute({ eventId, onOrderCreated }: { eventId: number; onOrderCreated: (orderId: number) => void }) {
  const [event, setEvent] = useState<EventDiscoveryDetail | null>(null);

  useEffect(() => {
    getDiscoverableEventDetail(eventId).then(setEvent).catch((err) => {
      const message = err instanceof ApiError ? err.message : 'Unable to load ticket tiers.';
      throw new Error(message);
    });
  }, [eventId]);

  if (!event) return <BootScreen />;
  return <TicketSelectionScreen event={event} onOrderCreated={onOrderCreated} />;
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
          <HomeScreen
            onOpenProfile={() => navigation.navigate('Profile')}
            onSignOut={signOut}
            onOpenEvent={(eventId) => navigation.navigate('EventDetail', { eventId })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="EventDetail">
        {({ route, navigation }) => (
          <EventDetailScreen
            eventId={route.params.eventId}
            onGetTickets={(event) => navigation.navigate('TicketSelection', { eventId: event.id })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="TicketSelection" options={{ title: 'Select tickets' }}>
        {({ route, navigation }) => (
          <TicketSelectionRoute
            eventId={route.params.eventId}
            onOrderCreated={(orderId) => navigation.navigate('CheckoutMethod', { eventId: route.params.eventId, orderId })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="CheckoutMethod" options={{ title: 'Checkout' }}>
        {({ route, navigation }) => (
          <CheckoutMethodScreen
            orderId={route.params.orderId}
            onOpenAgent={(referenceCode) =>
              navigation.navigate('MmgAgentCheckout', { eventId: route.params.eventId, orderId: route.params.orderId, referenceCode })
            }
            onResult={(title, message) =>
              navigation.navigate('PurchaseResult', { eventId: route.params.eventId, orderId: route.params.orderId, title, message })
            }
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="MmgAgentCheckout" options={{ title: 'MMG Agent' }}>
        {({ route, navigation }) => (
          <MmgAgentCheckoutScreen
            orderId={route.params.orderId}
            referenceCode={route.params.referenceCode}
            onResult={(title, message) =>
              navigation.navigate('PurchaseResult', { eventId: route.params.eventId, orderId: route.params.orderId, title, message })
            }
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="PurchaseResult" options={{ title: 'Purchase status' }}>
        {({ route, navigation }) => <PurchaseResultScreen title={route.params.title} message={route.params.message} onDone={() => navigation.navigate('Home')} />}
      </AppStack.Screen>
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
