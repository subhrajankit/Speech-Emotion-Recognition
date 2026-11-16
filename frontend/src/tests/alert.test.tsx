import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Alert } from '../components/ui/Alert';

// Chunk 9.4D: variant-aware ARIA semantics — info/success are polite status
// updates, warning/danger are assertive alerts. No redundant aria-live
// attributes (the roles already imply correct live-region behavior).

describe('Alert ARIA role by variant', () => {
  it('uses role="status" for info and success variants', () => {
    const info = renderToStaticMarkup(<Alert variant="info">note</Alert>);
    const success = renderToStaticMarkup(<Alert variant="success">done</Alert>);
    expect(info).toContain('role="status"');
    expect(success).toContain('role="status"');
    expect(info).not.toContain('role="alert"');
  });

  it('uses role="alert" for warning and danger variants', () => {
    const warning = renderToStaticMarkup(<Alert variant="warning">careful</Alert>);
    const danger = renderToStaticMarkup(<Alert variant="danger">bad</Alert>);
    const fallback = renderToStaticMarkup(<Alert>bad</Alert>);
    expect(warning).toContain('role="alert"');
    expect(danger).toContain('role="alert"');
    expect(fallback).toContain('role="alert"'); // default variant is danger
  });

  it('does not emit redundant aria-live attributes', () => {
    const html = renderToStaticMarkup(<Alert variant="info">note</Alert>);
    expect(html).not.toContain('aria-live');
  });
});

describe('Alert dismiss control', () => {
  it('defaults to a generic dismiss label', () => {
    const html = renderToStaticMarkup(
      <Alert onDismiss={() => {}}>msg</Alert>
    );
    expect(html).toContain('aria-label="Dismiss alert"');
  });

  it('supports a contextual dismissLabel to disambiguate coexisting alerts', () => {
    const html = renderToStaticMarkup(
      <Alert variant="info" dismissLabel="Dismiss no-speech notice" onDismiss={() => {}}>
        No speech detected.
      </Alert>
    );
    expect(html).toContain('aria-label="Dismiss no-speech notice"');
    expect(html).not.toContain('aria-label="Dismiss alert"');
  });
});
