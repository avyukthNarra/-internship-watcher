"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <section className="empty-state" role="alert"><h1>Something went wrong.</h1><p>We couldn’t load this page. Try again in a moment.</p><button className="primary-button" onClick={reset}>Try again</button></section>;
}
