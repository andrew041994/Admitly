export type AuthStackParamList = {
  SignIn: undefined;
  SignUp: undefined;
  ForgotPassword: undefined;
  ResetPassword: undefined;
};

export type AppStackParamList = {
  Home: undefined;
  EventDetail: { eventId: number };
  TicketSelection: { eventId: number };
  CheckoutMethod: { eventId: number; orderId: number };
  MmgAgentCheckout: { eventId: number; orderId: number; referenceCode: string };
  PurchaseResult: { eventId: number; orderId: number; title: string; message: string };
  MyTickets: undefined;
  TicketDetail: { ticketId: number };
  Scanner: { eventId: number; eventTitle: string };
  Profile: undefined;
  StaffEvents: undefined;
  CreateEvent: undefined;
  MyEvents: undefined;
  StaffManagement: undefined;
  OrganizerDashboard: { eventId: number };
};
