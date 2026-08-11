import React from 'react';
import ReactDOM from 'react-dom/client';
import * as Sentry from '@sentry/react';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from './app/router';
import './styles.css';
import { sentryDist, sentryDsn, sentryEnvironment, sentryRelease } from './lib/config';

if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: sentryEnvironment,
    release: sentryRelease,
    dist: sentryDist,
    sendDefaultPii: false,
  });
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  </React.StrictMode>,
);
