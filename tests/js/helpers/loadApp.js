import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..', '..');

const FIXTURE_HTML = `
<div id="navbar"></div>
<div id="announcement-bar" style="display:none"><span id="announcement-text"></span></div>
<div id="hero-carousel"></div><div id="hero-dots"></div>
<h2 id="weekly-title"></h2><p id="weekly-dates"></p><div id="weekly-grid"></div>
<div id="classics-grid"></div>
<div id="packs-grid"></div>
<h2 id="about-title"></h2><p id="about-text-content"></p>
<p id="pickup-address"></p><p id="delivery-info"></p><span id="delivery-fee-tag"></span>
<footer><span id="footer-year"></span><div id="social-icons"></div></footer>
<button id="cart-btn"></button><span id="cart-count">0</span>
<div id="cart-overlay"></div><div id="cart-sidebar"><div id="cart-items"></div><div id="cart-footer"><span id="cart-subtotal"></span></div></div>
<div id="item-modal"><span id="modal-title"></span><span id="modal-description"></span><span id="modal-calories"></span><span id="modal-rating"></span><span id="modal-price"></span><span id="modal-qty"></span></div>
<div id="checkout-modal"><div id="checkout-summary"></div><span id="pay-total"></span><div id="delivery-address-fields"></div><input id="checkout-name"><input id="checkout-email"><input id="checkout-phone"><div id="card-container"></div><div id="payment-status"></div><button id="pay-button"></button></div>
<div id="mobile-menu-overlay"></div>
`;

/**
 * Load app.js (and optionally square-payments.js) into the current jsdom window
 * in a way that exposes its top-level function/var declarations on `window`,
 * so tests can call them directly.
 */
export function loadApp({ withSquare = false } = {}) {
  document.body.innerHTML = FIXTURE_HTML;

  const appSrc = fs.readFileSync(path.join(ROOT, 'js/app.js'), 'utf8');
  // The production script uses `function` and `let`/`const` at top level,
  // which wouldn't attach to `window`. Evaluating indirectly at global scope
  // (via new Function wrapper) won't help — we use a Function constructor
  // that assigns locals back onto window.
  const exportedNames = [
    'init', 'renderHero', 'goToSlide', 'renderWeekly', 'renderClassics',
    'menuCard', 'renderPacks', 'renderAbout', 'renderFulfillment', 'renderFooter',
    'findItem', 'openItemModal', 'closeItemModal', 'changeModalQty', 'addFromModal',
    'loadCart', 'saveCart', 'quickAdd', 'addToCart', 'removeFromCart', 'changeCartQty',
    'getCartTotal', 'updateCartUI', 'toggleCart', 'goToCheckout', 'closeCheckout',
    'setCheckoutFulfillment', 'renderCheckoutSummary', 'selectFulfillment',
    'initScrollEffects', 'toggleMobileMenu', 'showPrivacyPolicy', 'showTerms',
  ];
  const exportedVars = ['siteContent', 'cart', 'currentSlide', 'modalItem', 'modalQty', 'selectedFulfillment'];

  const fnBridges = exportedNames
    .map((n) => `try { w['${n}'] = ${n}; } catch(_) {}`)
    .join('\n  ');
  const varBridges = exportedVars
    .map((n) => `try { Object.defineProperty(w, '${n}', { configurable: true, get: () => ${n}, set: (v) => { ${n} = v; } }); } catch(_) {}`)
    .join('\n  ');

  const wrapped = `
${appSrc}
;(function(){
  const w = typeof window !== 'undefined' ? window : globalThis;
  ${fnBridges}
  ${varBridges}
  w.__setCart = (c) => { cart = c; };
  w.__setContent = (c) => { siteContent = c; };
  w.__setFulfillment = (m) => { selectedFulfillment = m; };
})();
`;

  // eval in window scope so declarations become window globals where possible,
  // and assignments in the IIFE above ensure the rest are bridged.
  window.eval(wrapped);

  if (withSquare) {
    const sqSrc = fs.readFileSync(path.join(ROOT, 'js/square-payments.js'), 'utf8');
    const sqWrapped = `
${sqSrc}
;(function(){
  const w = typeof window !== 'undefined' ? window : globalThis;
  try { w.initSquarePayment = initSquarePayment; } catch(_) {}
  try { w.handlePayment = handlePayment; } catch(_) {}
  try { w.getCheckoutTotal = getCheckoutTotal; } catch(_) {}
})();`;
    window.eval(sqWrapped);
  }
}

export function sampleContent() {
  return JSON.parse(fs.readFileSync(path.join(ROOT, 'data/content.json'), 'utf8'));
}
