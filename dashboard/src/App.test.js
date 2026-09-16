/* Permanent routing regression coverage for App.js's react-router-dom usage.
Mounts a FRESH <App/> at each URL (mirrors this app's real navigation model:
the sidebar Menu uses plain <a href> full-page links, not react-router
<Link>/useNavigate - there is no client-side programmatic navigation to
cover). Each page component is mocked to a marker div so these tests
exercise routing/route-selection only, not each page's own behavior. */
import React from 'react';
import { act } from 'react-dom/test-utils';
import { createRoot } from 'react-dom/client';

jest.mock('./pages/Dashboard', () => () => <div data-testid="page-dashboard" />);
jest.mock('./pages/Companies', () => () => <div data-testid="page-companies" />);
jest.mock('./pages/Lenses', () => () => <div data-testid="page-lens-models" />);
jest.mock('./pages/Prescriptions', () => () => <div data-testid="page-prescriptions" />);
jest.mock('./pages/PDFPreview', () => () => <div data-testid="page-pdf-preview" />);
jest.mock('./pages/Backup', () => () => <div data-testid="page-backup" />);

const App = require('./App').default;

const ALL_TESTIDS = [
  'page-dashboard', 'page-companies', 'page-lens-models',
  'page-prescriptions', 'page-pdf-preview', 'page-backup',
];

let container;

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
});

afterEach(() => {
  act(() => { /* flush */ });
  document.body.removeChild(container);
  container = null;
});

function mountAt(path) {
  window.history.pushState({}, '', path);
  act(() => {
    createRoot(container).render(<App />);
  });
}

test.each([
  ['/', 'page-dashboard'],
  ['/companies', 'page-companies'],
  ['/lens-models', 'page-lens-models'],
  ['/prescriptions', 'page-prescriptions'],
  ['/pdf-preview', 'page-pdf-preview'],
  ['/backup', 'page-backup'],
])('route %s renders %s (fresh-load navigation model)', (path, testid) => {
  mountAt(path);
  expect(container.querySelector(`[data-testid="${testid}"]`)).not.toBeNull();
});

test('seller workflow route (/prescriptions) renders only the Prescriptions page', () => {
  mountAt('/prescriptions');
  expect(container.querySelector('[data-testid="page-prescriptions"]')).not.toBeNull();
  ALL_TESTIDS.filter((id) => id !== 'page-prescriptions').forEach((id) => {
    expect(container.querySelector(`[data-testid="${id}"]`)).toBeNull();
  });
});

test('unknown route matches no page (no catch-all Route defined today)', () => {
  mountAt('/this-route-does-not-exist');
  ALL_TESTIDS.forEach((id) => {
    expect(container.querySelector(`[data-testid="${id}"]`)).toBeNull();
  });
});

test('sidebar navigation uses plain application-relative <a href>, not external targets', () => {
  mountAt('/');
  const links = Array.from(container.querySelectorAll('a[href]'));
  expect(links.length).toBeGreaterThan(0);
  links.forEach((a) => {
    const href = a.getAttribute('href');
    expect(href.startsWith('/')).toBe(true); // application-relative only
    expect(href).not.toMatch(/^https?:\/\//i); // never an absolute external URL
    expect(href).not.toMatch(/^\/\//); // never protocol-relative
    expect(href).not.toContain('\\'); // never backslash-based path manipulation
  });
});
