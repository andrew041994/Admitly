import { Link, useLocation } from 'react-router-dom';

type LegalDocument = {
  title: string;
  intro: string;
  sections: Array<{ heading: string; body: string }>;
};

const updated = 'August 11, 2026';

const documents: Record<string, LegalDocument> = {
  privacy: {
    title: 'Privacy Policy',
    intro: 'This policy explains how Admitly handles information when people buy tickets, create or staff events, or administer our ticketing services.',
    sections: [
      { heading: 'Information we collect', body: 'We collect account and profile details, event and order records, payment references and status (not full payment credentials), support communications, device push tokens, request and network metadata, request IDs, rate-limit/security identifiers, application logs, and error telemetry. Location is processed only when a user chooses a location-based feature.' },
      { heading: 'Event-creator age and identity verification', body: 'Before an event can be approved, its creator may email a valid government-issued ID to Admitly solely so an administrator can verify identity and that the creator is at least 18. The ID image is not uploaded to or stored in the Admitly application or database and must be deleted from the verification email account as soon as verification is complete. Admitly retains only event/user verification status, verifier administrator ID, verification time, and an optional non-document audit note. The ID number should not be retained unless strictly necessary for a documented lawful reason.' },
      { heading: 'Credentials and device security', body: 'Passwords are stored as password hashes rather than readable passwords. The mobile application stores access and refresh credentials in secure device credential storage. Users remain responsible for securing their devices and account access.' },
      { heading: 'How we use information', body: 'We use information to operate accounts, review and publish events, sell and deliver tickets, process transfers and check-in, communicate service updates, prevent fraud and abuse, apply shared Redis-backed rate limits, support users, reconcile payments, comply with law, and improve reliability.' },
      { heading: 'Service providers and monitoring', body: 'We share only what is needed with event creators, messaging and push providers, infrastructure/database/object-storage vendors, Expo and mobile platform providers, Sentry for error monitoring, professional advisers, and authorities when legally required. Request IDs, logs, device details, and error context may be sent to Sentry, subject to configured data minimization. We do not sell personal information.' },
      { heading: 'Payment status', body: 'Live MMG payment processing is not currently enabled. Payment-related records may exist for development, review, reconciliation, or future provider integration, but this policy does not represent MMG as an active live processor. This policy will be updated before materially different live payment processing begins.' },
      { heading: 'Retention and security', body: 'We retain account, event, transaction, support, verification-audit, security, and error-monitoring records as needed for operational, financial, dispute, security, and legal purposes. No fixed retention period is promised here. We use access controls, encryption in transit, audit records, credential hashing, secure mobile credential storage, and service monitoring, but no system can guarantee absolute security.' },
      { heading: 'Your choices', body: 'You may update profile information, disable optional push or location features, and ask through the in-app support channel to access, correct, or delete eligible information. Some financial or security records must be retained.' },
      { heading: 'Guyana, international processing, and changes', body: 'Admitly handles personal information subject to applicable laws of Guyana. Service providers may process data outside Guyana, subject to applicable safeguards and contractual controls. Material policy changes will be posted here with a revised effective date.' },
    ],
  },
  refunds: {
    title: 'Refund Policy',
    intro: 'This policy applies subject to rights and remedies that cannot be waived under applicable Guyanese law.',
    sections: [
      { heading: 'Canceled events', body: 'Tickets are eligible for a full-order refund when an event is canceled, after Admitly verifies the event status, original order, payment, amount, and any prior refund or dispute. Admitly does not offer partial or per-ticket refunds. This does not limit any additional remedy required by applicable Guyanese law.' },
      { heading: 'Postponed, rescheduled, or changed events', body: 'A ticket remains valid for the announced rescheduled date or changed venue. A schedule or venue change alone does not automatically create a refund right, except where applicable law requires one.' },
      { heading: 'Change of plans or non-attendance', body: 'A buyer’s change of plans, inability to attend, or non-attendance does not create a discretionary refund right. Non-waivable rights under applicable Guyanese law remain unaffected.' },
      { heading: 'Who submits a request', body: 'Refund requests are handled through the original purchaser and order owner unless Admitly introduces another expressly supported lawful process. Ticket possession, a screenshot, or a transfer claim alone does not authorize a refund.' },
      { heading: 'Processing and disputes', body: 'Submit the order reference through support. Admitly will review payment, refund, transfer, check-in, cancellation, and dispute state before processing. Provider or financial-institution processing time may affect when an approved refund appears. Duplicate, ambiguous, or disputed claims may be held for investigation.' },
    ],
  },
  terms: {
    title: 'Terms of Service',
    intro: 'These terms govern access to Admitly. The Buyer Terms and Organizer Terms also apply when a user buys tickets or creates an event.',
    sections: [
      { heading: 'Using Admitly', body: 'You must provide accurate information, keep account credentials secure, and use the service only for lawful ticketing activity. Any authenticated user may create an event, but an event creator must be at least 18 and complete Admitly’s age and identity verification before that event may be approved or published.' },
      { heading: 'Event review', body: 'Event creators remain responsible for event accuracy, legality, safety, required permits and rights, and delivery. Admitly may withhold approval or publication until age and identity verification and event review are complete.' },
      { heading: 'Prohibited conduct', body: 'Do not abuse accounts or promotions, automate abusive traffic, interfere with security or check-in, resell contrary to event rules, upload unlawful content, impersonate others, or use tickets or payment references fraudulently.' },
      { heading: 'Accounts, security, and enforcement', body: 'Admitly may restrict or suspend an account, event, ticketing activity, or access where reasonably necessary to investigate abuse, fraud, security, safety, legal, or data-integrity concerns. Users must promptly report suspected unauthorized access.' },
      { heading: 'Electronic acceptance and communications', body: 'By creating an account, creating or purchasing for an event, or otherwise using Admitly after these terms are presented, you accept the applicable terms electronically. Admitly may provide transactional, security, event, and policy communications through the application, email, or enabled push notifications.' },
      { heading: 'Platform role and availability', body: 'Event creators are responsible for their events. Admitly provides ticketing and operational tools and may suspend features for safety, maintenance, legal compliance, or suspected abuse. Availability is not guaranteed without interruption.' },
      { heading: 'Content and intellectual property', body: 'Users retain ownership of their content and grant Admitly the limited rights needed to host, display, deliver, and promote the relevant event or service. Admitly software and branding remain protected.' },
      { heading: 'Enforcement and liability', body: 'We may restrict or terminate accounts that violate these terms and preserve evidence of abuse. To the extent permitted by law, liability is limited to direct losses reasonably connected to the service; rights that cannot legally be excluded remain unaffected.' },
      { heading: 'Governing law', body: 'These terms are governed by the applicable laws of Guyana. Nothing in these terms excludes a right, remedy, forum, or protection that cannot lawfully be waived, and disputes may be brought in any forum available under applicable law.' },
    ],
  },
  organizers: {
    title: 'Organizer Terms',
    intro: 'These additional terms apply when a user creates, publishes, manages, or staffs an event through Admitly.',
    sections: [
      { heading: 'Age and identity verification', body: 'An event creator must be at least 18. Before approving or publishing an event, Admitly requires the creator to email a valid government-issued ID for age and identity review. The ID image is not stored in the Admitly application or database and must be deleted from the verification email account after review; only verification audit metadata is retained.' },
      { heading: 'Event responsibility', body: 'Event creators must have authority to run the event and must provide accurate venue, schedule, price, inventory, accessibility, age, safety, refund, and restriction information. Required permits, insurance, taxes, safety measures, and rights are the event creator’s responsibility.' },
      { heading: 'Event access and editing', body: 'Any authenticated user may create an event. After creation, only that event’s creator or an Admitly administrator may edit it. Event staff and scanners do not receive event-edit authority merely from their operational assignment.' },
      { heading: 'Sales, fees, and payouts', body: 'Admitly will process the event creator’s payout, less applicable fees, within five business days after the event concludes. Processing may be delayed where reasonably necessary for reconciliation, fraud or security review, disputes, refunds, legal obligations, or incomplete payout information. This is an operational processing commitment; the current repository does not automate the five-business-day schedule.' },
      { heading: 'Changes, cancellations, and refunds', body: 'Event creators must promptly report changes or cancellation. Canceled events are eligible for full-order refunds subject to applicable Guyanese law; Admitly does not offer partial or per-ticket refunds. Tickets remain valid for a postponed or rescheduled date or changed venue, and a schedule or venue change alone does not automatically create a refund right except where law requires one.' },
      { heading: 'Staff and check-in', body: 'Event creators control staff access and are accountable for assigned permissions, devices, manual codes, overrides, and admission decisions. Suspicious scans or access must be reported promptly.' },
      { heading: 'Review and enforcement', body: 'Admitly may withhold event approval or publication until age/identity and event review are complete, and may suspend activity where reasonably necessary for fraud, security, safety, legal, refund, or data-integrity review. This does not create fee, reserve, or payout terms beyond those expressly stated.' },
    ],
  },
  buyers: {
    title: 'Buyer Terms',
    intro: 'These additional terms apply to ticket selection, checkout, ticket use, and transfers.',
    sections: [
      { heading: 'Orders and payment', body: 'An order is not complete until payment is verified. Holds and pending orders can expire. Buyers must review the event, ticket tier, quantity, displayed price, date, venue, and event-creator terms before paying. Live MMG payment processing is not currently enabled.' },
      { heading: 'Tickets and admission', body: 'Keep ticket codes confidential. A valid ticket does not override venue safety, identification, age, or entry rules. A ticket that is voided, refunded, transferred, duplicated, or already checked in may be rejected.' },
      { heading: 'Transfers', body: 'A transfer is complete only when confirmed by Admitly. Verify the intended recipient before submitting; completed transfers can affect control of the ticket and refund eligibility.' },
      { heading: 'Canceled events', body: 'Canceled-event tickets are eligible for a full-order refund after the original order and payment state are verified, subject to applicable Guyanese law. Admitly does not offer partial or per-ticket refunds. Refund requests are operationally handled through the original purchaser and order owner unless Admitly expressly supports another lawful process.' },
      { heading: 'Postponement, rescheduling, venue changes, and attendance', body: 'Tickets remain valid for an announced rescheduled date or changed venue. Postponement, rescheduling, a venue change, a change of plans, or non-attendance does not automatically create a discretionary refund right, except where applicable law requires one.' },
      { heading: 'Consumer rights', body: 'The Refund Policy applies. Nothing in these terms excludes or restricts rights or remedies that cannot be waived under applicable Guyanese law.' },
    ],
  },
};

export function LegalPage() {
  const pathname = useLocation().pathname;
  const document = ({
    '/privacy': 'privacy',
    '/refund-policy': 'refunds',
    '/organizer-terms': 'organizers',
    '/buyer-terms': 'buyers',
  } as Record<string, string>)[pathname] ?? 'terms';
  const legalDocument = documents[document] ?? documents.terms;
  return (
    <main className="legal-page">
      <article className="legal-card">
        <Link to="/" className="legal-brand">Admitly</Link>
        <h1>{legalDocument.title}</h1>
        <p className="legal-updated">Effective and last updated: {updated}</p>
        <p>{legalDocument.intro}</p>
        {legalDocument.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            <p>{section.body}</p>
          </section>
        ))}
        <section id="questions">
          <h2>Questions</h2>
          <p>Contact Admitly through the support channel in the application and include the relevant account or order reference.</p>
        </section>
        <nav className="legal-links" aria-label="Legal documents">
          <Link to="/privacy">Privacy</Link><Link to="/refund-policy">Refunds</Link><Link to="/terms">Terms</Link><Link to="/organizer-terms">Organizer terms</Link><Link to="/buyer-terms">Buyer terms</Link>
        </nav>
      </article>
    </main>
  );
}
