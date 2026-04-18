import { describe, it, expect, beforeEach } from 'vitest';
import { loadApp, sampleContent } from './helpers/loadApp.js';

describe('cart logic', () => {
  beforeEach(() => {
    localStorage.clear();
    loadApp();
    window.__setContent(sampleContent());
    window.__setCart([]);
  });

  it('addToCart adds a new item with qty', () => {
    window.addToCart('classic-1', 2);
    expect(window.cart).toEqual([{ id: 'classic-1', qty: 2 }]);
  });

  it('addToCart merges quantities for the same id', () => {
    window.addToCart('classic-1', 1);
    window.addToCart('classic-1', 3);
    expect(window.cart).toEqual([{ id: 'classic-1', qty: 4 }]);
  });

  it('removeFromCart strips an item', () => {
    window.addToCart('classic-1', 1);
    window.addToCart('classic-2', 1);
    window.removeFromCart('classic-1');
    expect(window.cart.map((c) => c.id)).toEqual(['classic-2']);
  });

  it('changeCartQty removes the item when it drops below 1', () => {
    window.addToCart('classic-1', 1);
    window.changeCartQty('classic-1', -1);
    expect(window.cart).toEqual([]);
  });

  it('getCartTotal multiplies price by qty across items', () => {
    window.__setCart([
      { id: 'classic-1', qty: 2 }, // $3.50 * 2 = $7.00
      { id: 'classic-3', qty: 1 }, // $3.75 * 1 = $3.75
    ]);
    expect(window.getCartTotal()).toBeCloseTo(10.75, 2);
  });

  it('getCartTotal ignores unknown ids silently (documents current behaviour)', () => {
    window.__setCart([
      { id: 'classic-1', qty: 1 }, // $3.50
      { id: 'does-not-exist', qty: 10 },
    ]);
    expect(window.getCartTotal()).toBeCloseTo(3.5, 2);
  });

  it('persists the cart to localStorage', () => {
    window.addToCart('classic-1', 1);
    expect(JSON.parse(localStorage.getItem('lb_cart'))).toEqual([
      { id: 'classic-1', qty: 1 },
    ]);
  });

  it('loadCart tolerates corrupted localStorage', () => {
    localStorage.setItem('lb_cart', 'not-json');
    window.loadCart();
    expect(window.cart).toEqual([]);
  });

  it('findItem resolves ids from both classics and weekly items', () => {
    expect(window.findItem('classic-1').name).toBe('Birthday Cake Ball');
    expect(window.findItem('weekly-1').name).toBe('Salted Caramel Pretzel Ball');
    expect(window.findItem('missing')).toBeUndefined();
  });
});
