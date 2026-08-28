const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const router = read('src/app/router.tsx');
const publicSite = read('src/components/PublicSite.tsx');
const siteHeader = read('src/components/SiteHeader.tsx');
const userShell = read('src/components/UserShell.tsx');
const landing = read('src/pages/LandingPage.tsx');
const eventsPage = read('src/pages/EventsPage.tsx');
const eventDetailPage = read('src/pages/EventDetailPage.tsx');
const myEventsPage = read('src/pages/MyEventsPage.tsx');
const styles = read('src/styles.css');
const session = read('src/lib/authSession.ts');
const client = read('src/lib/apiClient.ts');
const tickets = read('src/pages/TicketsPage.tsx');
const materialChange = read('src/pages/MaterialChangePage.tsx');
const main = read('src/main.tsx');
const login = read('src/pages/LoginPage.tsx');
const authApi = read('src/lib/authApi.ts');
const authContext = read('src/auth/AuthContext.tsx');
const account = read('src/pages/AccountPage.tsx');
const resetPasswordPage = read('src/pages/ResetPasswordRedirectPage.tsx');
const approvals = read('src/pages/EventApprovalsPage.tsx');
const approvalDetails = read('src/components/EventApprovalDetailsPanel.tsx');
const createEvent = read('src/pages/CreateEventPage.tsx');
const accountPage = read('src/pages/AccountPage.tsx');
const legalPage = read('src/pages/LegalPage.tsx');
const userApi = read('src/lib/userApi.ts');
const approvalsApi = read('src/lib/eventApprovalsApi.ts');
const sentryPrivacy = read('src/lib/sentryPrivacy.ts');
const backendEventSchema = fs.readFileSync(path.resolve(root, '../backend/app/schemas/event.py'), 'utf8');
const backendEventService = fs.readFileSync(path.resolve(root, '../backend/app/services/events.py'), 'utf8');
const backendEventApi = fs.readFileSync(path.resolve(root, '../backend/app/api/events.py'), 'utf8');

test('landing, discovery, detail, recovery, and legal routes remain public', () => {
  for (const route of ['/events', '/events/:eventId', '/login', '/signup', '/forgot-password', '/reset-password', '/verify-email', '/privacy', '/refund-policy', '/terms', '/organizer-terms', '/buyer-terms']) {
    assert.ok(router.includes(`path="${route}"`), route);
    assert.ok(router.indexOf(`path="${route}"`) < router.indexOf('<Route element={<RequireAuth />}'), route);
  }
  assert.match(router, /<Route index element={<LandingPage \/>}/);
});

test('user routes require auth and admin routes require backend-revalidated admin access', () => {
  for (const route of ['/tickets', '/transfers', '/notifications', '/account', '/create-event', '/my-events']) assert.ok(router.includes(`path="${route}"`));
  assert.match(router, /<Route element={<RequireAuth \/>}>/);
  assert.match(router, /validateAdminSession\(\)/);
  assert.match(router, /!user\?\.is_admin/);
  assert.match(router, /path="\/admin" element={<RequireAdmin \/>}/);
  assert.doesNotMatch(router, /<Route path="\/admin" element={<UserShell/);
});

test('browser session keeps access token in memory and refresh token tab-scoped', () => {
  assert.match(session, /let currentSession: AuthSession \| null = null/);
  assert.match(session, /window\.sessionStorage\.setItem\(refreshKey, tokens\.refresh_token\)/);
  assert.doesNotMatch(session, /localStorage\.setItem/);
  assert.match(session, /localStorage\.removeItem\(legacyAdminKey\)/);
  assert.match(client, /let refreshInFlight: Promise<boolean> \| null/);
  assert.match(client, /response\.status === 401/);
  assert.doesNotMatch(client, /response\.status === 403.*clearAuthSession/);
  assert.match(login, /!requestedDestination\.startsWith\('\/\/'\)/);
});

test('rotated refresh tokens replace storage and logout revokes before local clear', () => {
  assert.match(client, /setAuthSession\(payload\.user, payload\.tokens\)/);
  assert.match(authApi, /refresh_token: refreshToken/);
  assert.ok(authApi.indexOf("apiJson<{ success: boolean }>('/auth/logout'") < authApi.indexOf('clearAuthSession();'));
  assert.match(authApi, /\/auth\/logout-all/);
  assert.match(authContext, /try \{ await logout\(\); \} finally \{ setUser\(null\); setState\('signed-out'\); \}/);
  assert.match(authContext, /try \{ await logoutAll\(\); \} finally \{ setUser\(null\); setState\('signed-out'\); \}/);
  assert.match(account, /Log out all devices/);
  assert.match(account, /Password changed\. Sign in again/);
  assert.match(resetPasswordPage, /await signOut\(\)/);
  assert.match(resetPasswordPage, /All devices have been signed out/);
});

test('wallet uses backend canonical statuses and material changes use existing endpoint', () => {
  for (const label of ['Active', 'Used', 'Expired', 'Refunded']) assert.ok(tickets.includes(label));
  assert.match(tickets, /ticket\.display_status/);
  assert.match(materialChange, /rescheduleEvent\(id/);
  assert.match(materialChange, /useRef\(crypto\.randomUUID\(\)\)/);
  assert.match(materialChange, /idempotency_key: idempotencyKey\.current/);
  assert.match(materialChange, /Reschedule or Change Venue/);
});

test('My Events keeps only the empty-state page CTA', () => {
  const pageHeading = myEventsPage.slice(myEventsPage.indexOf('<div className="page-heading">'), myEventsPage.indexOf('{loading'));
  assert.doesNotMatch(pageHeading, /create-event|Create Event/);
  assert.match(myEventsPage, /<div className="empty-panel">[\s\S]*<Link className="button" to="\/create-event">Create Event<\/Link>/);
  assert.equal((myEventsPage.match(/<Link className="button" to="\/create-event">Create Event<\/Link>/g) || []).length, 1);
  assert.match(styles, /--admitly-primary: #2457f5/);
  assert.match(styles, /\.button \{[\s\S]*background: var\(--admitly-primary\)/);
  assert.match(styles, /\.button:not\(\.button-secondary\):not\(\.button-light\):not\(\.button-outline-light\):hover \{[\s\S]*background: var\(--admitly-primary-hover\)/);
});

test('authenticated header Create Event uses the same unmodified primary CTA class', () => {
  assert.match(siteHeader, /<NavLink className="button" to="\/create-event">Create Event<\/NavLink>/);
  assert.doesNotMatch(siteHeader, /className="button button-small" to="\/create-event"/);
  assert.match(styles, /\.user-actions > a:not\(\.button\)/);
});

test('public calls to action use web auth while mobile deep links remain available', () => {
  assert.match(publicSite, /<Link to="\/login">Log In<\/Link>/);
  assert.match(publicSite, /<Link[^>]*to="\/signup">Sign Up<\/Link>/);
  assert.match(publicSite, /attendeeLoginUrl = 'admitly:\/\/sign-in'/);
  assert.match(landing, /to="\/create-event"/);
});

test('signed-out event browsing renders guest login and signup navigation', () => {
  assert.match(publicSite, /state === 'signed-out'/);
  assert.match(publicSite, /<Link to="\/login">Log In<\/Link>/);
  assert.match(publicSite, /<Link[^>]*to="\/signup">Sign Up<\/Link>/);
  assert.match(eventsPage, /<PublicLayout>/);
});

test('signed-in public routes use the authenticated header instead of guest controls', () => {
  assert.match(publicSite, /if \(state === 'signed-in'\) return <AuthenticatedHeader \/>/);
  assert.ok(publicSite.indexOf("state === 'signed-in'") < publicSite.indexOf('<Link to="/login">Log In</Link>'));
  assert.match(siteHeader, />My Tickets<\/NavLink>/);
  assert.match(siteHeader, />My Events<\/NavLink>/);
  assert.match(siteHeader, />Account<\/NavLink>/);
});

test('signed-in admin keeps normal navigation and gains an admin dashboard link', () => {
  for (const label of ['Discover', 'My Tickets', 'My Events', 'Notifications', 'Account', 'Create Event']) {
    assert.ok(siteHeader.includes(`>${label}<`), label);
  }
  assert.match(siteHeader, /user\?\.is_admin \? <NavLink to="\/admin">Admin Dashboard<\/NavLink> : null/);
});

test('Discover and protected pages share one authenticated header and auth context', () => {
  assert.match(userShell, /<AuthenticatedHeader \/>/);
  assert.match(publicSite, /<AuthenticatedHeader \/>/);
  assert.match(siteHeader, /const \{ user, signOut \} = useAuth\(\)/);
  assert.doesNotMatch(`${publicSite}\n${siteHeader}\n${userShell}`, /useState<AuthState>|createContext/);
  assert.equal((main.match(/<AuthProvider>/g) || []).length, 1);
});

test('Discover links preserve the session and return directly to protected user pages', () => {
  assert.match(siteHeader, /<NavLink to="\/events">Discover<\/NavLink>/);
  for (const route of ['/tickets', '/my-events', '/notifications', '/account']) {
    assert.ok(siteHeader.includes(`to="${route}"`), route);
  }
  assert.doesNotMatch(siteHeader, /clearAuthSession|setAuthSession|sessionStorage|localStorage/);
});

test('event detail uses the same auth-aware public layout', () => {
  assert.match(eventDetailPage, /<PublicLayout>/);
  assert.match(eventDetailPage, /state === 'signed-out' \? <Link[^>]*to="\/login"/);
  assert.doesNotMatch(eventDetailPage, /state !== 'signed-in' \? <Link[^>]*to="\/login"/);
});

test('landing page stays public while using the auth-aware header and direct account CTAs', () => {
  assert.match(landing, /<PublicLayout>/);
  assert.match(landing, /to="\/create-event"/);
  assert.match(publicSite, /<Link to="\/tickets">My Tickets<\/Link>/);
});

test('logout from an auth-aware public page revokes and clears through existing auth flow', () => {
  assert.match(siteHeader, /await signOut\(\)/);
  assert.match(siteHeader, /navigate\('\/login', \{ replace: true/);
  assert.match(authContext, /try \{ await logout\(\); \} finally \{ setUser\(null\); setState\('signed-out'\); \}/);
  assert.ok(authApi.indexOf("apiJson<{ success: boolean }>('/auth/logout'") < authApi.indexOf('clearAuthSession();'));
});

test('public event routes stay outside authentication guards', () => {
  for (const route of ['/events', '/events/:eventId']) {
    assert.ok(router.indexOf(`path="${route}"`) < router.indexOf('<Route element={<RequireAuth />}'), route);
  }
});

test('public-page refresh restores auth without flashing guest controls and 403 does not sign out', () => {
  assert.match(publicSite, /state === 'booting'/);
  assert.match(publicSite, /Restoring your session/);
  assert.match(authContext, /const current = await apiJson<AuthUser>\('\/auth\/me'\)/);
  assert.match(client, /response\.status === 401/);
  assert.doesNotMatch(client, /response\.status === 403[\s\S]{0,160}clearAuthSession/);
});

test('all legal links remain discoverable and Sentry scrubs token-bearing URLs', () => {
  for (const route of ['/privacy', '/refund-policy', '/terms', '/organizer-terms', '/buyer-terms']) assert.ok(publicSite.includes(`to="${route}"`));
  assert.match(main, /sendDefaultPii: false/);
  assert.match(main, /beforeBreadcrumb/);
  assert.match(main, /beforeSend/);
});

test('creator verification remains account-scoped and revocable', () => {
  assert.match(approvalDetails, /Verify creator account as 18\+/);
  assert.match(approvalDetails, /Revoke account verification/);
  assert.match(approvals, /Already-approved events remain active/);
  assert.match(approvals, /getCreatorAgeIdentityVerificationHistory/);
  assert.match(createEvent, /account_verification_status/);
  assert.match(createEvent, /do not need to submit ID again/);
  assert.match(accountPage, /Age verification:/);
  assert.match(accountPage, /unless Admitly asks you to reverify/);
  assert.match(legalPage, /generally does not need to resubmit identification for each future event/);
});

test('Create Event offers private account verification for pending and revoked creators', () => {
  assert.match(createEvent, /Verify your age/);
  assert.match(createEvent, /Reverification required/);
  assert.match(createEvent, /Age verified/);
  assert.match(createEvent, /type="file" accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(createEvent, /allowed_content_types/);
  assert.match(createEvent, /max_upload_bytes/);
  assert.match(createEvent, /document_pending_review/);
  assert.match(createEvent, /ID submitted — awaiting review/);
  assert.match(createEvent, /upload_enabled/);
  assert.match(createEvent, /Online ID submission is temporarily unavailable/);
  assert.match(createEvent, /Create draft event/);
  assert.match(userApi, /\/account\/creator-verification\/document/);
  assert.match(userApi, /body\.append\('file', file, `verification-image\.\$\{extension\}`\)/);
  const verificationUploadApi = userApi.slice(userApi.indexOf('export const uploadCreatorVerificationDocument'), userApi.indexOf('export type OrganizerEvent'));
  assert.doesNotMatch(verificationUploadApi, /body\.append\('file', file\)/);
  assert.doesNotMatch(`${createEvent}\n${userApi}`, /localStorage|sessionStorage|readAsDataURL|base64/i);
  assert.match(sentryPrivacy, /'filename', 'fileName', 'file_name'/);
});

test('Create Event is a local two-step wizard that preserves event and tier state', () => {
  assert.match(createEvent, /useState<1 \| 2>\(1\)/);
  assert.match(createEvent, /Step \{step\} of 2/);
  const stepOneStart = createEvent.indexOf('{step === 1 ? <form');
  const stepTwoStart = createEvent.indexOf('</form> : <>', stepOneStart);
  const stepOne = createEvent.slice(stepOneStart, stepTwoStart);
  const stepTwo = createEvent.slice(stepTwoStart);
  assert.match(stepOne, />Next<\/button>/);
  assert.doesNotMatch(stepOne, /Upload ID|Create draft event|type="file"/);
  assert.match(stepTwo, /Upload ID/);
  assert.match(stepTwo, /Create draft event/);
  assert.match(stepTwo, />Back<\/button>/);
  assert.match(createEvent, /function next\(event: FormEvent\)[\s\S]*validateTiers\(tiers\)[\s\S]*setStep\(2\)/);
  assert.match(createEvent, /setStep\(1\)/);
  assert.ok(createEvent.indexOf('const [form, setForm]') < stepOneStart);
  assert.ok(createEvent.indexOf('const [tiers, setTiers]') < stepOneStart);
  const nextHandler = createEvent.slice(createEvent.indexOf('function next('), createEvent.indexOf('async function submit'));
  assert.doesNotMatch(nextHandler, /createEvent\(/);
});

test('admin document review is private, authorized, and releases memory-only image URLs', () => {
  assert.match(approvalsApi, /\/admin\/creator-verification\/documents\/\$\{documentId\}\/content/);
  assert.match(approvalsApi, /return response\.blob\(\)/);
  assert.match(approvals, /URL\.createObjectURL\(blob\)/);
  assert.match(approvals, /URL\.revokeObjectURL\(viewerUrlRef\.current\)/);
  assert.match(approvals, /Review private image/);
  assert.match(approvals, /viewer\?\.documentId !== document\.id/);
  assert.match(approvals, /hasPendingDocument=\{documents\.some\(\(document\) => document\.user_id === event\.creator_user_id\)\}/);
  assert.match(approvals, /Verify creator as 18\+/);
  assert.match(approvals, /Reject verification/);
  assert.match(approvals, /Retry cleanup/);
  assert.match(approvalsApi, /\/verify/);
  assert.match(approvalsApi, /\/reject/);
  assert.match(approvalsApi, /\/cleanup/);
  assert.doesNotMatch(`${approvals}\n${approvalsApi}`, /storage_object_key|signed_url|s3:\/\//i);
  assert.match(router, /path="\/admin" element={<RequireAdmin \/>}/);
});

test('expanded event approval uses a structured reusable review panel', () => {
  assert.match(approvals, /<EventApprovalDetailsPanel/);
  assert.match(approvals, /className="event-approval-expanded-row"/);
  assert.doesNotMatch(approvals, /<strong>Slug:<\/strong>/);
  for (const heading of ['Event details', 'Creator verification', 'Review actions', 'Verification history']) {
    assert.ok(approvalDetails.includes(`>${heading}<`), heading);
  }
  for (const label of ['Organizer', 'Start', 'Venue', 'Slug', 'Published', 'Event status', 'Creator user ID', 'Account verified at', 'Verifier', 'Approval snapshot']) {
    assert.ok(approvalDetails.includes(`label="${label}"`), label);
  }
  assert.match(approvalDetails, /StatusBadge label="Approval"/);
  assert.match(approvalDetails, /StatusBadge label="Creator"/);
  assert.match(approvalDetails, /onClick=\{onApprove\}/);
  assert.match(approvalDetails, /onClick=\{onCollapse\}>Hide details/);
  assert.ok(approvalDetails.indexOf('Required revocation reason') < approvalDetails.indexOf('onClick={onRevoke}'));
  assert.match(approvalDetails, /className="verification-timeline"/);
  assert.match(styles, /\.event-review-card-grid \{[\s\S]*grid-template-columns: repeat\(2/);
  assert.match(styles, /@media \(max-width: 850px\)[\s\S]*\.event-review-card-grid \{ grid-template-columns: 1fr/);
});

test('legal and creator guidance describe temporary private upload and remove email-only claims', () => {
  assert.doesNotMatch(`${legalPage}\n${landing}\n${createEvent}`, /verification by email|submitted separately by email|reviewed separately by email|verification email account/i);
  assert.match(legalPage, /restricted private storage/);
  assert.match(legalPage, /authorized administrator/);
  assert.match(legalPage, /seven-day storage lifecycle/);
  assert.match(legalPage, /does not intentionally retain date of birth or government ID number/);
  assert.match(legalPage, /generally does not need to resubmit identification for each future event/);
  assert.match(legalPage, /require reverification/);
});

test('web Create Event supports repeatable ticket tiers with backend-equivalent validation', () => {
  assert.match(createEvent, /useState<TierFormState\[]>\(\[initialTier\(\)\]\)/);
  assert.match(createEvent, /Add another ticket tier/);
  assert.match(createEvent, /tiers\.map\(\(tier, index\) =>/);
  assert.match(createEvent, /index > 0 \? <button/);
  assert.match(createEvent, /onClick=\{\(\) => removeTier\(index\)\}>Remove tier<\/button> : null/);
  assert.match(createEvent, /name is required/);
  assert.match(createEvent, /price must be zero or greater/);
  assert.match(createEvent, /quantity must be a positive integer/);
  assert.doesNotMatch(createEvent, /MAX_(?:TICKET_)?TIERS|tiers\.length\s*[>=]+\s*\d/);
});

test('web submits every tier in one atomic backend event-creation request', () => {
  assert.equal((createEvent.match(/await createEvent\(/g) || []).length, 1);
  assert.match(createEvent, /ticket_tiers: tiers\.map/);
  assert.match(createEvent, /if \(submissionInFlight\.current \|\| uploadingId\) return/);
  assert.match(createEvent, /submissionInFlight\.current = true/);
  const submitHandler = createEvent.slice(createEvent.indexOf('async function submit'), createEvent.indexOf('return <section'));
  assert.doesNotMatch(submitHandler, /verification.*===|document_pending_review/);
  assert.match(backendEventSchema, /ticket_tiers: list\["TicketTierCreateRequest"\] = Field\(min_length=1\)/);
  assert.match(backendEventService, /for idx, tier_payload in enumerate\(payload\.ticket_tiers\)/);
  assert.ok(backendEventApi.indexOf('create_event_with_ticket_tiers') < backendEventApi.indexOf('db.commit()', backendEventApi.indexOf('def create_event(')));
  assert.match(backendEventApi, /except EventCreationValidationError[\s\S]*db\.rollback\(\)/);
});
