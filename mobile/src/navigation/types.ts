export type AuthStackParamList = {
  SignIn: undefined;
  SignUp: undefined;
  ForgotPassword: undefined;
  ResetPassword: undefined;
};

export type AppStackParamList = {
  Home: undefined;
  EventDetail: { eventId: number };
  MyTickets: undefined;
  Profile: undefined;
};
