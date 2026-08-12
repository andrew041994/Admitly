import { NavigationContainer, DarkTheme, LinkingOptions, useNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as Notifications from 'expo-notifications';

import { useSession } from '../context/SessionContext';
import { theme } from '../theme';
import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { EventDiscoveryDetail, getDiscoverableEventDetail } from '../api/events';
import { AppStackParamList, AuthStackParamList } from './types';
import { BootScreen } from './screens/BootScreen';
import { EventDetailScreen } from './screens/EventDetailScreen';
import { CreateEventScreen } from './screens/CreateEventScreen';
import { ForgotPasswordScreen } from './screens/ForgotPasswordScreen';
import { HomeScreen } from './screens/HomeScreen';
import { ResetPasswordScreen } from './screens/ResetPasswordScreen';
import { SignInScreen } from './screens/SignInScreen';
import { SignUpScreen } from './screens/SignUpScreen';
import { VerifyEmailScreen } from './screens/VerifyEmailScreen';
import { PurchaseResultScreen } from './screens/PurchaseResultScreen';
import { MmgAgentCheckoutScreen } from './screens/MmgAgentCheckoutScreen';
import { MyTicketsScreen } from './screens/MyTicketsScreen';
import { TicketDetailScreen } from './screens/TicketDetailScreen';
import { CheckoutMethodScreen } from './screens/CheckoutMethodScreen';
import { TicketSelectionScreen } from './screens/TicketSelectionScreen';
import { ScannerScreen } from './screens/ScannerScreen';
import { MyEventsScreen } from './screens/MyEventsScreen';
import { OrganizerDashboardScreen } from './screens/OrganizerDashboardScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { StaffManagementScreen } from './screens/StaffManagementScreen';
import { StaffEventsScreen } from './screens/StaffEventsScreen';
import { NotificationsScreen } from './screens/NotificationsScreen';
import { RescheduleEventScreen } from './screens/RescheduleEventScreen';
import { registerPushTokenIfPermitted } from '../features/notifications/pushRegistration';
import { getNotificationDestination } from '../features/notifications/routing';

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const AppStack = createNativeStackNavigator<AppStackParamList>();

const linking: LinkingOptions<AuthStackParamList> = {
  prefixes: ['admitly://'],
  config: {
    screens: {
      SignIn: 'sign-in',
      SignUp: 'sign-up',
      ForgotPassword: 'forgot-password',
      ResetPassword: {
        path: 'reset-password',
        parse: {
          token: (token: string) => token,
        },
      },
      VerifyEmail: {
        path: 'verify-email',
        parse: {
          token: (token: string) => token,
        },
      },
    },
  },
};

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

function AuthNavigator({ verificationOnly = false }: { verificationOnly?: boolean }) {
  const { signOut, user } = useSession();
  return (
    <AuthStack.Navigator
      initialRouteName={verificationOnly ? 'VerifyEmail' : 'SignIn'}
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.primary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      {!verificationOnly ? <AuthStack.Screen name="SignIn" options={{ headerShown: false }}>
        {({ navigation }) => (
          <SignInScreen
            onGoToSignUp={() => navigation.navigate('SignUp')}
            onGoToForgotPassword={() => navigation.navigate('ForgotPassword')}
          />
        )}
      </AuthStack.Screen> : null}
      {!verificationOnly ? <AuthStack.Screen name="SignUp" options={{ headerShown: false }}>
        {({ navigation }) => <SignUpScreen onGoToSignIn={() => navigation.navigate('SignIn')} />}
      </AuthStack.Screen> : null}
      {!verificationOnly ? <AuthStack.Screen name="ForgotPassword" options={{ headerShown: false }}>
        {({ navigation }) => (
          <ForgotPasswordScreen
            onGoToSignIn={() => navigation.navigate('SignIn')}
            onGoToResetPassword={() => navigation.navigate('ResetPassword')}
          />
        )}
      </AuthStack.Screen> : null}
      {!verificationOnly ? <AuthStack.Screen name="ResetPassword" options={{ headerShown: false }}>
        {({ navigation, route }) => (
          <ResetPasswordScreen initialToken={route.params?.token} onGoToSignIn={() => navigation.navigate('SignIn')} />
        )}
      </AuthStack.Screen> : null}
      <AuthStack.Screen name="VerifyEmail" options={{ headerShown: false }}>
        {({ navigation, route }) => (
          <VerifyEmailScreen
            initialToken={route.params?.token}
            onGoToSignIn={() => {
              if (user) void signOut();
              else navigation.navigate('SignIn');
            }}
          />
        )}
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
  const { signOut, signOutAll, user } = useSession();
  const canAccessScanner = Boolean(user);
  const navigation = useNavigation<NativeStackNavigationProp<AppStackParamList>>();

  const openDestination = (destination: ReturnType<typeof getNotificationDestination>) => {
    if (!destination) return;
    if (destination.screen === 'TicketDetail') navigation.navigate('TicketDetail', destination.params);
    else if (destination.screen === 'EventDetail') navigation.navigate('EventDetail', destination.params);
    else navigation.navigate('MyTickets');
  };

  useEffect(() => {
    void registerPushTokenIfPermitted().catch(() => undefined);
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      openDestination(getNotificationDestination(response.notification.request.content.data));
    });
    void Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) {
        openDestination(getNotificationDestination(response.notification.request.content.data));
        void Notifications.clearLastNotificationResponseAsync();
      }
    });
    return () => subscription.remove();
  }, []);

  return (
    <AppStack.Navigator
      initialRouteName="Home"
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.primary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      <AppStack.Screen name="VerifyEmail" options={{ headerShown: false }}>
        {({ route }) => (
          <VerifyEmailScreen initialToken={route.params?.token} onGoToSignIn={() => void signOut()} />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="Home">
        {({ navigation }) => (
          <HomeScreen
            onOpenProfile={() => navigation.navigate('Profile')}
            onOpenMyTickets={() => navigation.navigate('MyTickets')}
            onOpenNotifications={() => navigation.navigate('Notifications')}
            onSignOut={signOut}
            onOpenEvent={(eventId) => navigation.navigate('EventDetail', { eventId })}
            onGetTickets={(eventId) => navigation.navigate('TicketSelection', { eventId })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="Notifications" options={{ title: 'Notifications' }}>
        {({ navigation }) => (
          <NotificationsScreen
            onOpenNotification={(notification) => openDestination(getNotificationDestination({
              route_key: notification.route_key,
              route_params: notification.route_params,
            }))}
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
      <AppStack.Screen name="MyTickets" options={{ title: 'My Tickets' }}>
        {({ navigation }) => (
          <MyTicketsScreen
            onOpenTicket={(ticketId) => navigation.navigate('TicketDetail', { ticketId })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="TicketDetail" options={{ title: 'Ticket' }}>
        {({ route }) => (
          <TicketDetailScreen ticketId={route.params.ticketId} />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="Scanner" options={{ headerShown: false }}>
        {({ route, navigation }) => (
          <ScannerScreen
            canAccessScanner={canAccessScanner}
            eventId={route.params.eventId}
            eventTitle={route.params.eventTitle}
            onBack={() => navigation.goBack()}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="Profile" options={{ title: 'Profile' }}>
        {({ navigation }) => (
          <ProfileScreen
            onSignOut={signOut}
            onSignOutAll={signOutAll}
            onOpenCreateEvent={() => navigation.navigate('CreateEvent')}
            onOpenMyEvents={() => navigation.navigate('MyEvents')}
            onOpenStaffManagement={() => navigation.navigate('StaffManagement')}
            onOpenStaffEvents={() => navigation.navigate('StaffEvents')}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="StaffEvents" options={{ title: 'Events I’m Working' }}>
        {({ navigation }) => (
          <StaffEventsScreen
            onOpenScanner={(eventId, eventTitle) => navigation.navigate('Scanner', { eventId, eventTitle })}
          />
        )}
      </AppStack.Screen>
      <AppStack.Screen name="CreateEvent" options={{ title: 'Create Event' }}>
        {({ navigation }) => <CreateEventScreen onCreated={(eventId) => navigation.replace('OrganizerDashboard', { eventId })} />}
      </AppStack.Screen>
      <AppStack.Screen name="MyEvents" options={{ title: 'My Events' }}>
        {({ navigation }) => <MyEventsScreen onOpenEvent={(eventId) => navigation.navigate('OrganizerDashboard', { eventId })} />}
      </AppStack.Screen>
      <AppStack.Screen name="StaffManagement" component={StaffManagementScreen} options={{ title: 'Staff Management' }} />
      <AppStack.Screen name="OrganizerDashboard" options={{ title: 'Event Dashboard' }}>
        {({ route, navigation }) => <OrganizerDashboardScreen eventId={route.params.eventId} onOpenReschedule={() => navigation.navigate('RescheduleEvent', { eventId: route.params.eventId })} />}
      </AppStack.Screen>
      <AppStack.Screen name="RescheduleEvent" options={{ title: 'Reschedule or Change Venue' }}>
        {({ route, navigation }) => <RescheduleEventScreen eventId={route.params.eventId} onCompleted={() => navigation.replace('OrganizerDashboard', { eventId: route.params.eventId })} />}
      </AppStack.Screen>
    </AppStack.Navigator>
  );
}

export function RootNavigator() {
  const { state, user } = useSession();

  return (
    <NavigationContainer theme={navTheme} linking={linking}>
      {state === 'booting' ? (
        <BootScreen />
      ) : state === 'signedOut' ? (
        <AuthNavigator />
      ) : user?.requires_email_verification ? (
        <AuthNavigator verificationOnly />
      ) : (
        <SignedInNavigator />
      )}
    </NavigationContainer>
  );
}
