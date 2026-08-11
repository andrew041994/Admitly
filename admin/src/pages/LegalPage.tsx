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
    intro: 'This policy explains how Admitly handles information when buyers, organizers, staff, and administrators use our ticketing services.',
    sections: [
      { heading: 'Information we collect', body: 'We collect account and profile details, event and order records, payment references and status (not full payment credentials), support communications, device push tokens, security logs, and location only when a user opts into location-based features.' },
      { heading: 'How we use information', body: 'We use information to operate accounts, sell and deliver tickets, process transfers and check-in, communicate service updates, prevent fraud, support users, reconcile payments, comply with law, and improve reliability.' },
      { heading: 'Sharing', body: 'We share only what is needed with event organizers, payment and messaging providers, infrastructure vendors, professional advisers, and authorities when legally required. We do not sell personal information.' },
      { heading: 'Retention and security', body: 'We retain records for operational, financial, dispute, security, and legal needs, then delete or de-identify them when no longer required. We use access controls, encryption in transit, audit records, and service monitoring, but no system can guarantee absolute security.' },
      { heading: 'Your choices', body: 'You may update profile information, disable optional push or location features, and ask through the in-app support channel to access, correct, or delete eligible information. Some financial or security records must be retained.' },
      { heading: 'International processing and changes', body: 'Service providers may process data outside your location with appropriate safeguards. Material changes will be posted here with a revised effective date.' },
    ],
  },
  refunds: {
    title: 'Refund Policy',
    intro: 'Ticket refund eligibility depends on the event policy, event status, payment settlement, and applicable law.',
    sections: [
      { heading: 'Buyer-requested refunds', body: 'Unless the event listing or applicable law says otherwise, completed ticket purchases are final. Submit a request through support with the order reference; submitting a request does not guarantee approval.' },
      { heading: 'Canceled or materially changed events', body: 'When an organizer cancels an event or authorizes a refund batch, Admitly will notify affected buyers and process eligible amounts after funds and event status are verified. Postponed or rescheduled events are handled under the organizer policy and applicable law.' },
      { heading: 'Fees and timing', body: 'The approved refund amount may exclude service or payment fees where permitted. Provider processing times vary, and the receiving account may take additional time to display the credit.' },
      { heading: 'Transfers, disputes, and duplicate claims', body: 'Only the current eligible ticket or order owner may request a refund. Transferred, checked-in, voided, previously refunded, or disputed tickets may be ineligible. Chargeback activity can pause a refund while the payment is investigated.' },
    ],
  },
  terms: {
    title: 'Terms of Service',
    intro: 'These terms govern access to Admitly. The Buyer Terms and Organizer Terms also apply to those roles.',
    sections: [
      { heading: 'Using Admitly', body: 'You must provide accurate information, keep account credentials secure, meet applicable age and legal requirements, and use the service only for lawful ticketing activity.' },
      { heading: 'Prohibited conduct', body: 'Do not abuse accounts or promotions, automate abusive traffic, interfere with security or check-in, resell contrary to event rules, upload unlawful content, impersonate others, or use tickets or payment references fraudulently.' },
      { heading: 'Platform role and availability', body: 'Organizers are responsible for their events. Admitly provides ticketing and operational tools and may suspend features for safety, maintenance, legal compliance, or suspected abuse. Availability is not guaranteed without interruption.' },
      { heading: 'Content and intellectual property', body: 'Users retain ownership of their content and grant Admitly the limited rights needed to host, display, deliver, and promote the relevant event or service. Admitly software and branding remain protected.' },
      { heading: 'Enforcement and liability', body: 'We may restrict or terminate accounts that violate these terms and preserve evidence of abuse. To the extent permitted by law, liability is limited to direct losses reasonably connected to the service; rights that cannot legally be excluded remain unaffected.' },
    ],
  },
  organizers: {
    title: 'Organizer Terms',
    intro: 'These additional terms apply when creating, publishing, managing, or staffing an event through Admitly.',
    sections: [
      { heading: 'Event responsibility', body: 'Organizers must have authority to run the event and must provide accurate venue, schedule, price, inventory, accessibility, age, safety, refund, and restriction information. Required permits, insurance, taxes, and rights are the organizer’s responsibility.' },
      { heading: 'Sales and funds', body: 'Sales, fees, reserves, refunds, disputes, reversals, and payouts are recorded in Admitly financial ledgers and remain subject to provider settlement and reconciliation. Organizers must not treat unsettled amounts as final.' },
      { heading: 'Changes, cancellations, and refunds', body: 'Organizers must promptly report material changes or cancellations, fund required refunds, cooperate with buyer communications, and not evade obligations by removing an event or account.' },
      { heading: 'Staff and check-in', body: 'Organizers control staff access and are accountable for assigned permissions, devices, manual codes, overrides, and admission decisions. Suspicious scans or access must be reported promptly.' },
      { heading: 'Review and enforcement', body: 'Admitly may review events, request supporting documents, delay publication or settlement, hold reserves, remove content, or suspend activity where fraud, safety, legal, refund, or reputational risks are reasonably identified.' },
    ],
  },
  buyers: {
    title: 'Buyer Terms',
    intro: 'These additional terms apply to ticket selection, checkout, ticket use, and transfers.',
    sections: [
      { heading: 'Orders and payment', body: 'An order is not complete until payment is verified. Holds and pending orders can expire. Buyers must review the event, ticket tier, quantity, price, fees, date, venue, and organizer terms before paying.' },
      { heading: 'Tickets and admission', body: 'Keep ticket codes confidential. A valid ticket does not override venue safety, identification, age, or entry rules. A ticket that is voided, refunded, transferred, duplicated, or already checked in may be rejected.' },
      { heading: 'Transfers', body: 'A transfer is complete only when confirmed by Admitly. Verify the intended recipient before submitting; completed transfers can affect control of the ticket and refund eligibility.' },
      { heading: 'Refunds and event issues', body: 'The Refund Policy applies. Event delivery remains the organizer’s responsibility, but Admitly may assist with records, communications, reconciliation, and approved refund processing.' },
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
        <Link to="/terms" className="legal-brand">Admitly</Link>
        <h1>{legalDocument.title}</h1>
        <p className="legal-updated">Effective and last updated: {updated}</p>
        <p>{legalDocument.intro}</p>
        {legalDocument.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            <p>{section.body}</p>
          </section>
        ))}
        <section>
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
