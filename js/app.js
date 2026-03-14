/* ===== Le Besian Balls — Main Application ===== */

let siteContent = null;
let cart = [];
let currentSlide = 0;
let heroInterval = null;
let modalItem = null;
let modalQty = 1;
let selectedFulfillment = 'pickup';

// ── Bootstrap ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);

async function init() {
    try {
        const res = await fetch('data/content.json');
        siteContent = await res.json();
    } catch (e) {
        console.error('Failed to load content:', e);
        return;
    }
    renderHero();
    renderWeekly();
    renderClassics();
    renderPacks();
    renderAbout();
    renderFulfillment();
    renderFooter();
    loadCart();
    initScrollEffects();
}

// ── Hero Carousel ──────────────────────────────────────────
function renderHero() {
    const carousel = document.getElementById('hero-carousel');
    const dotsContainer = document.getElementById('hero-dots');
    const { hero } = siteContent;

    carousel.innerHTML = hero.slides.map((slide, i) => `
        <div class="hero-slide ${i === 0 ? 'active' : ''}" style="background:${slide.bg_color || hero.background_color}">
            <h1>${slide.title}</h1>
            <p>${slide.subtitle}</p>
            <a href="${hero.cta_link}" class="btn btn-primary">${hero.cta_text}</a>
        </div>
    `).join('');

    dotsContainer.innerHTML = hero.slides.map((_, i) =>
        `<div class="hero-dot ${i === 0 ? 'active' : ''}" onclick="goToSlide(${i})"></div>`
    ).join('');

    if (hero.slides.length > 1) {
        heroInterval = setInterval(() => goToSlide((currentSlide + 1) % hero.slides.length), 5000);
    }
}

function goToSlide(idx) {
    const slides = document.querySelectorAll('.hero-slide');
    const dots = document.querySelectorAll('.hero-dot');
    slides[currentSlide].classList.remove('active');
    dots[currentSlide].classList.remove('active');
    currentSlide = idx;
    slides[currentSlide].classList.add('active');
    dots[currentSlide].classList.add('active');
    clearInterval(heroInterval);
    heroInterval = setInterval(() => goToSlide((currentSlide + 1) % slides.length), 5000);
}

// ── Menu Rendering ─────────────────────────────────────────
function renderWeekly() {
    const { weekly } = siteContent.menu;
    document.getElementById('weekly-title').textContent = weekly.week_label;
    document.getElementById('weekly-dates').textContent = weekly.date_range;
    document.getElementById('weekly-grid').innerHTML = weekly.items.map(item => menuCard(item)).join('');
}

function renderClassics() {
    document.getElementById('classics-grid').innerHTML =
        siteContent.menu.classics.map(item => menuCard(item)).join('');
}

function menuCard(item) {
    const tagHtml = item.tag ? `<span class="menu-card-tag">${item.tag}</span>` : '';
    return `
        <div class="menu-card" onclick="openItemModal('${item.id}')">
            <div class="menu-card-image">
                ${tagHtml}
                <div class="placeholder-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d4619c" stroke-width="1.5">
                        <circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>
                    </svg>
                </div>
            </div>
            <div class="menu-card-body">
                <h3>${item.name}</h3>
                <p class="description">${item.description}</p>
                <div class="menu-card-footer">
                    <span class="menu-card-price">$${item.price.toFixed(2)}</span>
                    <div class="menu-card-meta">
                        <span class="menu-card-rating"><span class="star">★</span> ${item.rating}</span>
                        <span>${item.calories} cal</span>
                    </div>
                </div>
                <button class="add-to-cart-btn" onclick="event.stopPropagation(); quickAdd('${item.id}')" title="Add to order">+</button>
            </div>
        </div>
    `;
}

// ── Packs ──────────────────────────────────────────────────
function renderPacks() {
    document.getElementById('packs-grid').innerHTML = siteContent.packs.map(pack => `
        <div class="pack-card">
            <h3>${pack.name}</h3>
            <p>${pack.description}</p>
            ${pack.discount > 0 ? `<span class="pack-discount">Save ${pack.discount}%</span>` : ''}
        </div>
    `).join('');
}

// ── About ──────────────────────────────────────────────────
function renderAbout() {
    const { about } = siteContent;
    document.getElementById('about-title').textContent = about.title;
    document.getElementById('about-text-content').textContent = about.text;
}

// ── Fulfillment ────────────────────────────────────────────
function renderFulfillment() {
    const { fulfillment } = siteContent;
    document.getElementById('pickup-address').textContent = fulfillment.pickup_address;
    const deliveryInfo = `Within ${fulfillment.delivery_radius_miles} miles`;
    document.getElementById('delivery-info').textContent = deliveryInfo;
    const feeText = fulfillment.delivery_fee > 0
        ? `$${fulfillment.delivery_fee.toFixed(2)} (Free over $${fulfillment.free_delivery_minimum.toFixed(2)})`
        : 'Free';
    document.getElementById('delivery-fee-tag').textContent = feeText;
}

// ── Footer ─────────────────────────────────────────────────
function renderFooter() {
    document.getElementById('footer-year').textContent = new Date().getFullYear();
    const { social } = siteContent;
    const icons = [];
    if (social.instagram) icons.push(`<a href="${social.instagram}" class="social-icon" target="_blank" rel="noopener">IG</a>`);
    if (social.facebook) icons.push(`<a href="${social.facebook}" class="social-icon" target="_blank" rel="noopener">FB</a>`);
    if (social.tiktok) icons.push(`<a href="${social.tiktok}" class="social-icon" target="_blank" rel="noopener">TT</a>`);
    document.getElementById('social-icons').innerHTML = icons.join('');

    // Announcements
    const { announcements } = siteContent;
    if (announcements && announcements.length > 0) {
        document.getElementById('announcement-bar').style.display = 'block';
        document.getElementById('announcement-text').textContent = announcements[0];
    }
}

// ── Find Item Helper ───────────────────────────────────────
function findItem(id) {
    const all = [...siteContent.menu.classics, ...siteContent.menu.weekly.items];
    return all.find(i => i.id === id);
}

// ── Item Modal ─────────────────────────────────────────────
function openItemModal(id) {
    modalItem = findItem(id);
    if (!modalItem) return;
    modalQty = 1;
    document.getElementById('modal-title').textContent = modalItem.name;
    document.getElementById('modal-description').textContent = modalItem.description;
    document.getElementById('modal-calories').textContent = `${modalItem.calories} cal`;
    document.getElementById('modal-rating').innerHTML = `<span class="star">★</span> ${modalItem.rating} (${modalItem.reviews} reviews)`;
    document.getElementById('modal-price').textContent = `$${modalItem.price.toFixed(2)}`;
    document.getElementById('modal-qty').textContent = '1';
    document.getElementById('item-modal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeItemModal() {
    document.getElementById('item-modal').style.display = 'none';
    document.body.style.overflow = '';
    modalItem = null;
}

function changeModalQty(delta) {
    modalQty = Math.max(1, modalQty + delta);
    document.getElementById('modal-qty').textContent = modalQty;
}

function addFromModal() {
    if (!modalItem) return;
    addToCart(modalItem.id, modalQty);
    closeItemModal();
}

// ── Cart Logic ─────────────────────────────────────────────
function loadCart() {
    try {
        const saved = localStorage.getItem('lb_cart');
        if (saved) cart = JSON.parse(saved);
    } catch (_) { cart = []; }
    updateCartUI();
}

function saveCart() {
    localStorage.setItem('lb_cart', JSON.stringify(cart));
    updateCartUI();
}

function quickAdd(id) {
    addToCart(id, 1);
}

function addToCart(id, qty) {
    const existing = cart.find(c => c.id === id);
    if (existing) {
        existing.qty += qty;
    } else {
        cart.push({ id, qty });
    }
    saveCart();
    // pulse the cart icon
    const btn = document.getElementById('cart-btn');
    btn.classList.add('pulse');
    setTimeout(() => btn.classList.remove('pulse'), 300);
}

function removeFromCart(id) {
    cart = cart.filter(c => c.id !== id);
    saveCart();
}

function changeCartQty(id, delta) {
    const item = cart.find(c => c.id === id);
    if (!item) return;
    item.qty += delta;
    if (item.qty < 1) {
        removeFromCart(id);
        return;
    }
    saveCart();
}

function getCartTotal() {
    return cart.reduce((sum, c) => {
        const item = findItem(c.id);
        return item ? sum + item.price * c.qty : sum;
    }, 0);
}

function updateCartUI() {
    const count = cart.reduce((s, c) => s + c.qty, 0);
    document.getElementById('cart-count').textContent = count;
    const itemsContainer = document.getElementById('cart-items');
    const footer = document.getElementById('cart-footer');

    if (cart.length === 0) {
        itemsContainer.innerHTML = '<p class="cart-empty">Your cart is empty</p>';
        footer.style.display = 'none';
        return;
    }

    footer.style.display = 'block';
    itemsContainer.innerHTML = cart.map(c => {
        const item = findItem(c.id);
        if (!item) return '';
        return `
            <div class="cart-item">
                <div class="cart-item-image">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#d4619c" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>
                </div>
                <div class="cart-item-details">
                    <div class="cart-item-name">${item.name}</div>
                    <div class="cart-item-price">$${(item.price * c.qty).toFixed(2)}</div>
                    <div class="cart-item-qty">
                        <button onclick="changeCartQty('${c.id}', -1)">-</button>
                        <span>${c.qty}</span>
                        <button onclick="changeCartQty('${c.id}', 1)">+</button>
                    </div>
                    <div class="cart-item-remove" onclick="removeFromCart('${c.id}')">Remove</div>
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('cart-subtotal').textContent = `$${getCartTotal().toFixed(2)}`;
}

function toggleCart() {
    document.getElementById('cart-overlay').classList.toggle('open');
    document.getElementById('cart-sidebar').classList.toggle('open');
}

// ── Checkout ───────────────────────────────────────────────
function goToCheckout() {
    if (cart.length === 0) return;
    toggleCart();
    renderCheckoutSummary();
    document.getElementById('checkout-modal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    // Initialize Square payment form
    if (typeof initSquarePayment === 'function') {
        initSquarePayment();
    }
}

function closeCheckout() {
    document.getElementById('checkout-modal').style.display = 'none';
    document.body.style.overflow = '';
}

function setCheckoutFulfillment(method) {
    selectedFulfillment = method;
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.method === method);
    });
    document.getElementById('delivery-address-fields').style.display = method === 'delivery' ? 'block' : 'none';
    renderCheckoutSummary();
}

function renderCheckoutSummary() {
    const subtotal = getCartTotal();
    const { fulfillment } = siteContent;
    const deliveryFee = selectedFulfillment === 'delivery' && subtotal < fulfillment.free_delivery_minimum
        ? fulfillment.delivery_fee : 0;
    const total = subtotal + deliveryFee;

    let html = cart.map(c => {
        const item = findItem(c.id);
        return item ? `<div class="order-summary-row"><span>${item.name} x${c.qty}</span><span>$${(item.price * c.qty).toFixed(2)}</span></div>` : '';
    }).join('');

    if (deliveryFee > 0) {
        html += `<div class="order-summary-row"><span>Delivery Fee</span><span>$${deliveryFee.toFixed(2)}</span></div>`;
    }
    html += `<div class="order-summary-row total"><span>Total</span><span>$${total.toFixed(2)}</span></div>`;

    document.getElementById('checkout-summary').innerHTML = html;
    document.getElementById('pay-total').textContent = `$${total.toFixed(2)}`;
}

function selectFulfillment(method) {
    selectedFulfillment = method;
    document.querySelector(`[data-method="${method}"]`)?.click();
    document.getElementById('order').scrollIntoView({ behavior: 'smooth' });
}

// ── Scroll Effects ─────────────────────────────────────────
function initScrollEffects() {
    window.addEventListener('scroll', () => {
        const navbar = document.getElementById('navbar');
        navbar.classList.toggle('scrolled', window.scrollY > 10);
    });
}

// ── Mobile Menu ────────────────────────────────────────────
function toggleMobileMenu() {
    document.getElementById('mobile-menu-overlay').classList.toggle('open');
}

// ── Placeholder legal pages ────────────────────────────────
function showPrivacyPolicy() {
    alert('Privacy Policy page — to be added. You can link to a separate privacy-policy.html page.');
}
function showTerms() {
    alert('Terms & Conditions page — to be added. You can link to a separate terms.html page.');
}
