import { describe, it, expect, beforeEach } from 'vitest';
import { loadApp, sampleContent } from './helpers/loadApp.js';

describe('renderers', () => {
  beforeEach(() => {
    localStorage.clear();
    loadApp();
    window.__setContent(sampleContent());
  });

  it('renderHero produces one slide per content entry', () => {
    window.renderHero();
    const slides = document.querySelectorAll('.hero-slide');
    const dots = document.querySelectorAll('.hero-dot');
    expect(slides.length).toBe(sampleContent().hero.slides.length);
    expect(dots.length).toBe(slides.length);
    expect(slides[0].classList.contains('active')).toBe(true);
  });

  it('renderWeekly writes title, date range and grid items', () => {
    window.renderWeekly();
    const content = sampleContent();
    expect(document.getElementById('weekly-title').textContent).toBe(content.menu.weekly.week_label);
    expect(document.getElementById('weekly-dates').textContent).toBe(content.menu.weekly.date_range);
    const cards = document.querySelectorAll('#weekly-grid .menu-card');
    expect(cards.length).toBe(content.menu.weekly.items.length);
  });

  it('renderClassics renders a card per classic item', () => {
    window.renderClassics();
    const content = sampleContent();
    const cards = document.querySelectorAll('#classics-grid .menu-card');
    expect(cards.length).toBe(content.menu.classics.length);
  });

  it('renderFulfillment formats delivery fee correctly', () => {
    window.renderFulfillment();
    // $5.00 (Free over $35.00)
    expect(document.getElementById('delivery-fee-tag').textContent)
      .toBe('$5.00 (Free over $35.00)');
  });

  it('renderFooter fills in social links when provided', () => {
    window.renderFooter();
    const anchors = document.querySelectorAll('#social-icons a');
    expect(anchors.length).toBe(3); // IG, FB, TT
    expect(anchors[0].getAttribute('href')).toBe('https://instagram.com/lebesianballs');
  });
});

describe('XSS exposure (regression markers)', () => {
  beforeEach(() => {
    localStorage.clear();
    loadApp();
    const c = sampleContent();
    c.menu.classics[0].name = '<img src=x onerror="window.__PWNED=1">';
    window.__setContent(c);
  });

  it('DOCUMENTS that menuCard currently injects unsanitised item.name (see js/app.js:81-107)', () => {
    window.renderClassics();
    // The injected <img> tag is present because the renderer uses innerHTML
    // with interpolated fields. onerror won't run in jsdom without loading,
    // but the DOM shape confirms the vulnerability.
    const img = document.querySelector('#classics-grid img[onerror]');
    expect(img).not.toBeNull();
    // When this assertion starts failing, sanitisation has been added — update the test.
  });
});
