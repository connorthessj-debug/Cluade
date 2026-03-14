/* ===== Le Besian Balls — Admin Dashboard ===== */

let content = null;
let isDirty = false;

document.addEventListener('DOMContentLoaded', loadContent);

// ── Load Content ───────────────────────────────────────────
async function loadContent() {
    try {
        const res = await fetch('../api/admin-api.php?action=load');
        if (!res.ok) throw new Error('API not available');
        content = await res.json();
    } catch (e) {
        // Fallback: load directly from JSON file
        try {
            const res = await fetch('../data/content.json');
            content = await res.json();
        } catch (e2) {
            alert('Failed to load content data.');
            return;
        }
    }
    renderAll();
}

function renderAll() {
    renderHero();
    renderWeeklyItems();
    renderClassicsItems();
    renderPacks();
    renderAbout();
    renderSite();
    renderFulfillment();
    renderAnnouncements();
}

// ── Save ───────────────────────────────────────────────────
async function saveAll() {
    const statusEl = document.getElementById('save-status');
    statusEl.textContent = 'Saving...';
    statusEl.className = 'save-status';

    // Collect all form data back into content object
    collectHero();
    collectWeekly();
    collectClassics();
    collectPacks();
    collectAbout();
    collectSite();
    collectFulfillment();
    collectAnnouncements();

    try {
        const res = await fetch('../api/admin-api.php?action=save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(content)
        });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = 'Saved!';
            statusEl.className = 'save-status saved';
            isDirty = false;
        } else {
            throw new Error(data.error || 'Save failed');
        }
    } catch (e) {
        // Fallback for static hosting: save to localStorage
        localStorage.setItem('lb_admin_content', JSON.stringify(content));
        statusEl.textContent = 'Saved to local storage (PHP API not available)';
        statusEl.className = 'save-status saved';
        isDirty = false;
        console.warn('Backend API not available, saved to localStorage. Set up the PHP API for persistent saves.');
    }

    setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

function markDirty() {
    isDirty = true;
    document.getElementById('save-status').textContent = 'Unsaved changes';
    document.getElementById('save-status').className = 'save-status dirty';
}

// ── Section Navigation ─────────────────────────────────────
function showSection(id) {
    document.querySelectorAll('.admin-section').forEach(s => s.style.display = 'none');
    document.getElementById(`section-${id}`).style.display = 'block';
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-section="${id}"]`).classList.add('active');
    const titles = { hero:'Hero Section', weekly:'Weekly Flavors', classics:'Classic Menu',
        packs:'Packs & Pricing', about:'Our Story', site:'Site Settings',
        fulfillment:'Fulfillment', announcements:'Announcements' };
    document.getElementById('page-title').textContent = titles[id] || id;
    // Close mobile sidebar
    document.querySelector('.sidebar').classList.remove('open');
}

function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
}

// ── Hero ───────────────────────────────────────────────────
function renderHero() {
    const h = content.hero;
    document.getElementById('hero-cta-text').value = h.cta_text;
    document.getElementById('hero-cta-link').value = h.cta_link;
    document.getElementById('hero-bg-color').value = h.background_color;
    renderHeroSlides();
}

function renderHeroSlides() {
    const container = document.getElementById('hero-slides-list');
    container.innerHTML = content.hero.slides.map((slide, i) => `
        <div class="editable-item">
            <div class="item-header">
                <h4>Slide ${i + 1}</h4>
                <div class="item-actions">
                    <button class="btn btn-danger btn-sm" onclick="removeHeroSlide(${i})">Delete</button>
                </div>
            </div>
            <div class="form-group">
                <label>Title</label>
                <input type="text" value="${esc(slide.title)}" data-slide="${i}" data-field="title" onchange="markDirty()">
            </div>
            <div class="form-group">
                <label>Subtitle</label>
                <input type="text" value="${esc(slide.subtitle)}" data-slide="${i}" data-field="subtitle" onchange="markDirty()">
            </div>
            <div class="form-group">
                <label>Background Color</label>
                <input type="color" value="${slide.bg_color}" data-slide="${i}" data-field="bg_color" onchange="markDirty()">
            </div>
        </div>
    `).join('');
}

function addHeroSlide() {
    content.hero.slides.push({ title: 'New Slide', subtitle: 'Edit this slide', bg_color: '#f9e8f0' });
    renderHeroSlides();
    markDirty();
}

function removeHeroSlide(i) {
    content.hero.slides.splice(i, 1);
    renderHeroSlides();
    markDirty();
}

function collectHero() {
    content.hero.cta_text = document.getElementById('hero-cta-text').value;
    content.hero.cta_link = document.getElementById('hero-cta-link').value;
    content.hero.background_color = document.getElementById('hero-bg-color').value;
    document.querySelectorAll('#hero-slides-list [data-slide]').forEach(input => {
        const i = parseInt(input.dataset.slide);
        const field = input.dataset.field;
        if (content.hero.slides[i]) content.hero.slides[i][field] = input.value;
    });
}

// ── Menu Items (Weekly & Classics) ─────────────────────────
function renderWeeklyItems() {
    document.getElementById('weekly-label').value = content.menu.weekly.week_label;
    document.getElementById('weekly-dates').value = content.menu.weekly.date_range;
    renderMenuItems('weekly', content.menu.weekly.items, 'weekly-items-list');
}

function renderClassicsItems() {
    renderMenuItems('classics', content.menu.classics, 'classics-items-list');
}

function renderMenuItems(type, items, containerId) {
    const container = document.getElementById(containerId);
    container.innerHTML = items.map((item, i) => `
        <div class="editable-item">
            <div class="item-header">
                <h4>${esc(item.name)}</h4>
                <div class="item-actions">
                    <button class="btn btn-danger btn-sm" onclick="removeMenuItem('${type}', ${i})">Delete</button>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" value="${esc(item.name)}" data-type="${type}" data-idx="${i}" data-field="name" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Price ($)</label>
                    <input type="number" step="0.01" value="${item.price}" data-type="${type}" data-idx="${i}" data-field="price" onchange="markDirty()">
                </div>
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea data-type="${type}" data-idx="${i}" data-field="description" rows="2" onchange="markDirty()">${esc(item.description)}</textarea>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Calories</label>
                    <input type="number" value="${item.calories}" data-type="${type}" data-idx="${i}" data-field="calories" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Rating</label>
                    <input type="number" step="0.1" min="0" max="5" value="${item.rating}" data-type="${type}" data-idx="${i}" data-field="rating" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Reviews</label>
                    <input type="number" value="${item.reviews}" data-type="${type}" data-idx="${i}" data-field="reviews" onchange="markDirty()">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Image Path</label>
                    <input type="text" value="${esc(item.image)}" data-type="${type}" data-idx="${i}" data-field="image" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Tag (e.g. NEW, FAN FAVORITE)</label>
                    <input type="text" value="${esc(item.tag || '')}" data-type="${type}" data-idx="${i}" data-field="tag" onchange="markDirty()">
                </div>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" ${item.available ? 'checked' : ''} data-type="${type}" data-idx="${i}" data-field="available" onchange="markDirty()">
                    Available
                </label>
            </div>
        </div>
    `).join('');
}

function addMenuItem(type) {
    const newItem = {
        id: `${type}-${Date.now()}`,
        name: 'New Item',
        description: 'Description here',
        price: 3.50,
        calories: 200,
        image: 'assets/images/placeholder.jpg',
        rating: 5.0,
        reviews: 0,
        available: true,
        tag: ''
    };
    if (type === 'weekly') {
        content.menu.weekly.items.push(newItem);
        renderWeeklyItems();
    } else {
        content.menu.classics.push(newItem);
        renderClassicsItems();
    }
    markDirty();
}

function removeMenuItem(type, idx) {
    if (!confirm('Remove this item?')) return;
    if (type === 'weekly') {
        content.menu.weekly.items.splice(idx, 1);
        renderWeeklyItems();
    } else {
        content.menu.classics.splice(idx, 1);
        renderClassicsItems();
    }
    markDirty();
}

function collectWeekly() {
    content.menu.weekly.week_label = document.getElementById('weekly-label').value;
    content.menu.weekly.date_range = document.getElementById('weekly-dates').value;
    collectMenuFields('weekly', content.menu.weekly.items);
}

function collectClassics() {
    collectMenuFields('classics', content.menu.classics);
}

function collectMenuFields(type, items) {
    document.querySelectorAll(`[data-type="${type}"]`).forEach(el => {
        const idx = parseInt(el.dataset.idx);
        const field = el.dataset.field;
        if (!items[idx]) return;
        if (field === 'available') {
            items[idx][field] = el.checked;
        } else if (['price', 'calories', 'rating', 'reviews'].includes(field)) {
            items[idx][field] = parseFloat(el.value) || 0;
        } else {
            items[idx][field] = el.value;
        }
    });
}

// ── Packs ──────────────────────────────────────────────────
function renderPacks() {
    const container = document.getElementById('packs-list');
    container.innerHTML = content.packs.map((pack, i) => `
        <div class="editable-item">
            <div class="item-header">
                <h4>${esc(pack.name)}</h4>
                <button class="btn btn-danger btn-sm" onclick="removePack(${i})">Delete</button>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" value="${esc(pack.name)}" data-pack="${i}" data-field="name" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Count</label>
                    <input type="number" value="${pack.count}" data-pack="${i}" data-field="count" onchange="markDirty()">
                </div>
                <div class="form-group">
                    <label>Discount %</label>
                    <input type="number" value="${pack.discount}" data-pack="${i}" data-field="discount" onchange="markDirty()">
                </div>
            </div>
            <div class="form-group">
                <label>Description</label>
                <input type="text" value="${esc(pack.description)}" data-pack="${i}" data-field="description" onchange="markDirty()">
            </div>
        </div>
    `).join('');
}

function addPack() {
    content.packs.push({ name: 'New Pack', count: 1, discount: 0, description: '' });
    renderPacks();
    markDirty();
}

function removePack(i) {
    content.packs.splice(i, 1);
    renderPacks();
    markDirty();
}

function collectPacks() {
    document.querySelectorAll('[data-pack]').forEach(el => {
        const i = parseInt(el.dataset.pack);
        const field = el.dataset.field;
        if (!content.packs[i]) return;
        if (['count', 'discount'].includes(field)) {
            content.packs[i][field] = parseInt(el.value) || 0;
        } else {
            content.packs[i][field] = el.value;
        }
    });
}

// ── About ──────────────────────────────────────────────────
function renderAbout() {
    document.getElementById('about-title').value = content.about.title;
    document.getElementById('about-text').value = content.about.text;
    document.getElementById('about-image').value = content.about.image;
}

function collectAbout() {
    content.about.title = document.getElementById('about-title').value;
    content.about.text = document.getElementById('about-text').value;
    content.about.image = document.getElementById('about-image').value;
}

// ── Site Settings ──────────────────────────────────────────
function renderSite() {
    document.getElementById('site-name').value = content.site.name;
    document.getElementById('site-tagline').value = content.site.tagline;
    document.getElementById('site-description').value = content.site.description;
    document.getElementById('site-phone').value = content.site.phone;
    document.getElementById('site-email').value = content.site.email;
    document.getElementById('site-address').value = content.site.address;
    document.getElementById('social-instagram').value = content.social.instagram;
    document.getElementById('social-facebook').value = content.social.facebook;
    document.getElementById('social-tiktok').value = content.social.tiktok;
}

function collectSite() {
    content.site.name = document.getElementById('site-name').value;
    content.site.tagline = document.getElementById('site-tagline').value;
    content.site.description = document.getElementById('site-description').value;
    content.site.phone = document.getElementById('site-phone').value;
    content.site.email = document.getElementById('site-email').value;
    content.site.address = document.getElementById('site-address').value;
    content.social.instagram = document.getElementById('social-instagram').value;
    content.social.facebook = document.getElementById('social-facebook').value;
    content.social.tiktok = document.getElementById('social-tiktok').value;
}

// ── Fulfillment ────────────────────────────────────────────
function renderFulfillment() {
    document.getElementById('fulfill-pickup').value = content.fulfillment.pickup_address;
    document.getElementById('fulfill-radius').value = content.fulfillment.delivery_radius_miles;
    document.getElementById('fulfill-fee').value = content.fulfillment.delivery_fee;
    document.getElementById('fulfill-free-min').value = content.fulfillment.free_delivery_minimum;
}

function collectFulfillment() {
    content.fulfillment.pickup_address = document.getElementById('fulfill-pickup').value;
    content.fulfillment.delivery_radius_miles = parseInt(document.getElementById('fulfill-radius').value) || 0;
    content.fulfillment.delivery_fee = parseFloat(document.getElementById('fulfill-fee').value) || 0;
    content.fulfillment.free_delivery_minimum = parseFloat(document.getElementById('fulfill-free-min').value) || 0;
}

// ── Announcements ──────────────────────────────────────────
function renderAnnouncements() {
    const container = document.getElementById('announcements-list');
    container.innerHTML = (content.announcements || []).map((text, i) => `
        <div class="editable-item">
            <div class="item-header">
                <h4>Announcement ${i + 1} ${i === 0 ? '(Active)' : ''}</h4>
                <button class="btn btn-danger btn-sm" onclick="removeAnnouncement(${i})">Delete</button>
            </div>
            <div class="form-group">
                <input type="text" value="${esc(text)}" data-announcement="${i}" onchange="markDirty()">
            </div>
        </div>
    `).join('');
}

function addAnnouncement() {
    if (!content.announcements) content.announcements = [];
    content.announcements.push('New announcement — edit me!');
    renderAnnouncements();
    markDirty();
}

function removeAnnouncement(i) {
    content.announcements.splice(i, 1);
    renderAnnouncements();
    markDirty();
}

function collectAnnouncements() {
    content.announcements = [];
    document.querySelectorAll('[data-announcement]').forEach(el => {
        content.announcements.push(el.value);
    });
}

// ── Utility ────────────────────────────────────────────────
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Warn on unsaved changes
window.addEventListener('beforeunload', e => {
    if (isDirty) { e.preventDefault(); e.returnValue = ''; }
});
