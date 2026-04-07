import { FormEvent, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import { fetchEventMessages, sendEventBroadcast } from '../lib/messagingApi';

export function MessagingPage() {
  const [eventId, setEventId] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [includeEmail, setIncludeEmail] = useState(true);
  const [includePush, setIncludePush] = useState(true);
  const [messages, setMessages] = useState<any[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadHistory = async () => {
    if (!eventId) return;
    setMessages(await fetchEventMessages(Number(eventId)));
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    try {
      const result = await sendEventBroadcast(Number(eventId), {
        subject,
        body,
        include_email: includeEmail,
        include_push: includePush,
      });
      setFeedback(`Send attempted to ${result.attempted_recipients} attendee(s).`);
      await loadHistory();
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.detail : 'Failed to send update.');
    }
  };

  return (
    <section className="support-page">
      <div className="card">
        <h2>Event Messaging</h2>
        <label>Event ID<input value={eventId} onChange={(e) => setEventId(e.target.value)} /></label>
        <button onClick={loadHistory}>Load history</button>
      </div>
      <div className="card">
        <h3>Send event update</h3>
        <form onSubmit={onSend} className="notes-form">
          <input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <textarea placeholder="Operational update" value={body} onChange={(e) => setBody(e.target.value)} />
          <label><input type="checkbox" checked={includeEmail} onChange={(e) => setIncludeEmail(e.target.checked)} /> Email</label>
          <label><input type="checkbox" checked={includePush} onChange={(e) => setIncludePush(e.target.checked)} /> Push</label>
          <button type="submit">Send update</button>
        </form>
        {feedback ? <p>{feedback}</p> : null}
      </div>
      <div className="card">
        <h3>History</h3>
        <ul className="list-reset">
          {messages.map((m) => (
            <li key={m.id}>{new Date(m.created_at).toLocaleString()} · {m.template_type} · {m.channel} · {m.status} ({m.provider_status || 'n/a'})</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
