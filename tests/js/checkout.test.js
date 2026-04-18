import { describe, it, expect, beforeEach } from 'vitest';
import { loadApp, sampleContent } from './helpers/loadApp.js';

describe('checkout math', () => {
  beforeEach(() => {
    localStorage.clear();
    loadApp({ withSquare: true });
    window.__setContent(sampleContent());
    window.__setCart([]);
  });

  it('renderCheckoutSummary: pickup has no delivery fee', () => {
    window.__setCart([{ id: 'classic-1', qty: 2 }]); // $7.00
    window.__setFulfillment('pickup');
    window.renderCheckoutSummary();
    expect(document.getElementById('pay-total').textContent).toBe('$7.00');
  });

  it('renderCheckoutSummary: delivery under minimum adds fee', () => {
    window.__setCart([{ id: 'classic-1', qty: 1 }]); // $3.50, minimum is $35
    window.__setFulfillment('delivery');
    window.renderCheckoutSummary();
    // 3.50 + 5.00 delivery fee
    expect(document.getElementById('pay-total').textContent).toBe('$8.50');
  });

  it('renderCheckoutSummary: delivery over minimum is free', () => {
    window.__setCart([{ id: 'classic-1', qty: 11 }]); // $38.50 > $35 minimum
    window.__setFulfillment('delivery');
    window.renderCheckoutSummary();
    expect(document.getElementById('pay-total').textContent).toBe('$38.50');
  });

  it('getCheckoutTotal mirrors renderCheckoutSummary math', () => {
    window.__setCart([{ id: 'classic-1', qty: 1 }]);
    window.__setFulfillment('delivery');
    expect(window.getCheckoutTotal()).toBeCloseTo(8.5, 2);

    window.__setFulfillment('pickup');
    expect(window.getCheckoutTotal()).toBeCloseTo(3.5, 2);
  });
});
