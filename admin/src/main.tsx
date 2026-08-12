import React from 'react';
import ReactDOM from 'react-dom/client';
import * as Sentry from '@sentry/react';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from './app/router';
import './styles.css';
import { sentryDist, sentryDsn, sentryEnvironment, sentryRelease } from './lib/config';
import { AuthProvider } from './auth/AuthContext';
import { scrubSentryBreadcrumb, scrubSentryEvent } from './lib/sentryPrivacy';

if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: sentryEnvironment,
    release: sentryRelease,
    dist: sentryDist,
    sendDefaultPii: false,
    beforeBreadcrumb: (breadcrumb) => scrubSentryBreadcrumb(breadcrumb),
    beforeSend: (event) => scrubSentryEvent(event),
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider><AppRouter /></AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
