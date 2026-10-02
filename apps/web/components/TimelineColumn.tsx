import type { TimelineEvent } from "@/lib/types";

type Props = { events: TimelineEvent[]; pending: boolean };

export function TimelineColumn({ events, pending }: Props) {
  return (
    <section className="column" aria-labelledby="timeline-heading">
      <h2 id="timeline-heading">Timeline</h2>
      {pending ? (
        <p className="working" role="status">
          Worker is computing a new decision...
        </p>
      ) : null}
      <ol className="events">
        {events.map((event) => (
          <li key={event.id} data-testid="timeline-event">
            <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString()}</time>
            <span>{event.message}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
