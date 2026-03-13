/**
 * Cold Email AI Optimizer - Dashboard Frontend
 *
 * Fetches data from api.php and renders charts + tables.
 */

const API = 'api.php';

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    loadScoreTrend();
    loadIndustryChart();
    loadWeightChart();
    loadTopEmails();
    loadLearnings();

    // Industry filter
    const filter = document.getElementById('industry-filter');
    if (filter) {
        filter.addEventListener('change', () => loadTopEmails(filter.value));
    }

    // Auto-refresh every 5 minutes
    setInterval(() => {
        loadScoreTrend();
        loadTopEmails();
        loadLearnings();
        refreshStats();
    }, 300000);
});

// --- API Helper ---
async function fetchAPI(action, params = {}) {
    const url = new URL(API, window.location.href);
    url.searchParams.set('action', action);
    for (const [k, v] of Object.entries(params)) {
        url.searchParams.set(k, v);
    }
    const res = await fetch(url);
    return res.json();
}

// --- Score Trend Chart ---
let scoreTrendChart = null;

async function loadScoreTrend() {
    const data = await fetchAPI('iterations', { limit: 50 });
    if (!data || !data.length) return;

    // Sort by iteration_num ascending
    data.sort((a, b) => a.iteration_num - b.iteration_num);

    const labels = data.map(d => `#${d.iteration_num}`);
    const avgScores = data.map(d => parseFloat(d.avg_score));
    const bestScores = data.map(d => parseFloat(d.best_score));

    const ctx = document.getElementById('scoreTrendChart');
    if (!ctx) return;

    if (scoreTrendChart) scoreTrendChart.destroy();

    scoreTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Best Score',
                    data: bestScores,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                },
                {
                    label: 'Avg Score',
                    data: avgScores,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#8b8d9a' },
                },
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#8b8d9a' },
                },
            },
            plugins: {
                legend: {
                    labels: { color: '#e4e4e7' },
                },
            },
        },
    });
}

// --- Industry Performance Chart ---
let industryChart = null;

async function loadIndustryChart() {
    const data = await fetchAPI('stats');
    if (!data || !data.by_industry || !data.by_industry.length) return;

    const labels = data.by_industry.map(d => d.industry);
    const avgScores = data.by_industry.map(d => parseFloat(d.avg_score));
    const bestScores = data.by_industry.map(d => parseFloat(d.best_score));

    const ctx = document.getElementById('industryChart');
    if (!ctx) return;

    if (industryChart) industryChart.destroy();

    industryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Avg Score',
                    data: avgScores,
                    backgroundColor: 'rgba(99, 102, 241, 0.7)',
                    borderRadius: 4,
                },
                {
                    label: 'Best Score',
                    data: bestScores,
                    backgroundColor: 'rgba(34, 197, 94, 0.7)',
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#8b8d9a' },
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#8b8d9a', maxRotation: 45 },
                },
            },
            plugins: {
                legend: {
                    labels: { color: '#e4e4e7' },
                },
            },
        },
    });
}

// --- Weight Evolution Chart ---
let weightChart = null;

async function loadWeightChart() {
    const data = await fetchAPI('weights');
    if (!data || !data.length) return;

    const labels = data.map(d => `#${d.iteration_num}`);
    const weightKeys = [
        'subject_line_quality', 'hook_type_score', 'personalization_depth',
        'cta_clarity', 'email_length_score', 'timing_score', 'spam_avoidance'
    ];
    const colors = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899'];
    const readableNames = [
        'Subject Line', 'Hook Type', 'Personalization',
        'CTA Clarity', 'Email Length', 'Timing', 'Spam Avoidance'
    ];

    const datasets = weightKeys.map((key, i) => ({
        label: readableNames[i],
        data: data.map(d => parseFloat(d[key]) * 100),
        borderColor: colors[i],
        backgroundColor: colors[i] + '20',
        fill: false,
        tension: 0.3,
        pointRadius: 2,
    }));

    const ctx = document.getElementById('weightChart');
    if (!ctx) return;

    if (weightChart) weightChart.destroy();

    weightChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 40,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#8b8d9a',
                        callback: v => v + '%',
                    },
                },
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#8b8d9a' },
                },
            },
            plugins: {
                legend: {
                    labels: { color: '#e4e4e7', boxWidth: 12 },
                },
            },
        },
    });
}

// --- Top Emails Table ---
async function loadTopEmails(industry = '') {
    const params = { limit: 20 };
    if (industry) params.industry = industry;

    const data = await fetchAPI('top_emails', params);
    const tbody = document.getElementById('top-emails-body');
    if (!tbody) return;

    if (!data || !data.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading">No emails found</td></tr>';
        return;
    }

    tbody.innerHTML = data.map(email => {
        const score = parseFloat(email.total_score);
        const scoreClass = score >= 70 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';

        return `
            <tr>
                <td><span class="score-badge ${scoreClass}">${score.toFixed(1)}</span></td>
                <td>${escapeHtml(email.industry)}</td>
                <td>${escapeHtml(email.subject_line)}</td>
                <td><span class="hook-badge">${escapeHtml(email.hook_type)}</span></td>
                <td>#${email.iteration_num}</td>
                <td><button class="btn-view" onclick="viewEmail(${email.id})">View</button></td>
            </tr>
        `;
    }).join('');
}

// --- Learnings Feed ---
async function loadLearnings() {
    const data = await fetchAPI('learnings', { limit: 20 });
    const container = document.getElementById('learnings-container');
    if (!container) return;

    if (!data || !data.length) {
        container.innerHTML = '<p class="loading">No learnings yet</p>';
        return;
    }

    container.innerHTML = data.map(l => `
        <div class="learning-card">
            <div class="learning-meta">Iteration #${l.iteration_num} &mdash; ${formatDate(l.created_at)}</div>
            <div class="learning-text">${escapeHtml(l.insight)}</div>
        </div>
    `).join('');
}

// --- Email Detail Modal ---
async function viewEmail(id) {
    const email = await fetchAPI('email_detail', { id });
    if (!email || email.error) return;

    const score = parseFloat(email.total_score);
    const scoreClass = score >= 70 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';

    const scoreItems = [
        ['Subject Line', email.subject_score],
        ['Hook Type', email.hook_score],
        ['Personalization', email.personalization_score],
        ['CTA Clarity', email.cta_score],
        ['Email Length', email.length_score],
        ['Timing', email.timing_score],
        ['Spam Avoidance', email.spam_score],
    ];

    document.getElementById('modal-body').innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <span class="score-badge ${scoreClass}" style="font-size:1.2rem;padding:4px 12px">${score.toFixed(1)}</span>
            <span class="hook-badge">${escapeHtml(email.hook_type)}</span>
            <span style="color:var(--text-muted);font-size:0.85rem">${escapeHtml(email.industry)} &mdash; Iteration #${email.iteration_num}</span>
        </div>
        <div class="email-detail-subject">${escapeHtml(email.subject_line)}</div>
        <div class="email-detail-body">${escapeHtml(email.body)}</div>
        <h3 style="font-size:0.95rem;margin-bottom:8px">Score Breakdown</h3>
        <div class="score-breakdown">
            ${scoreItems.map(([label, val]) => {
                const v = parseFloat(val);
                const cls = v >= 70 ? 'score-high' : v >= 50 ? 'score-mid' : 'score-low';
                return `<div class="score-item"><span class="score-item-label">${label}</span><span class="score-item-value ${cls}">${v.toFixed(1)}</span></div>`;
            }).join('')}
        </div>
    `;

    document.getElementById('email-modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('email-modal').classList.add('hidden');
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-backdrop')) closeModal();
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// --- Refresh Stats ---
async function refreshStats() {
    const data = await fetchAPI('stats');
    if (!data) return;

    const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    set('stat-iterations', data.total_iterations);
    set('stat-emails', data.total_emails);
    set('stat-best', data.best_score_ever);
    set('stat-avg', data.avg_score_overall);
    set('stat-learnings', data.total_learnings);
}

// --- Utilities ---
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
