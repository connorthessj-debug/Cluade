<?php
/**
 * Cold Email AI Optimizer - Dashboard
 *
 * Single-page dashboard showing optimization progress, top emails,
 * weight evolution, and AI learnings. Fully self-contained HTML.
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';

// Preload data for initial render (avoids flash of empty content)
try {
    $stats = get_stats();
    $has_data = $stats['total_iterations'] > 0;
} catch (Exception $e) {
    $stats = null;
    $has_data = false;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cold Email AI Optimizer</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <!-- Header -->
    <header>
        <div class="header-content">
            <h1>Cold Email AI Optimizer</h1>
            <div class="header-stats">
                <div class="stat-chip">
                    <span class="stat-label">Iterations</span>
                    <span class="stat-value" id="stat-iterations"><?= $stats['total_iterations'] ?? 0 ?></span>
                </div>
                <div class="stat-chip">
                    <span class="stat-label">Emails Generated</span>
                    <span class="stat-value" id="stat-emails"><?= $stats['total_emails'] ?? 0 ?></span>
                </div>
                <div class="stat-chip">
                    <span class="stat-label">Best Score</span>
                    <span class="stat-value" id="stat-best"><?= $stats['best_score_ever'] ?? '--' ?></span>
                </div>
                <div class="stat-chip">
                    <span class="stat-label">Avg Score</span>
                    <span class="stat-value" id="stat-avg"><?= $stats['avg_score_overall'] ?? '--' ?></span>
                </div>
                <div class="stat-chip">
                    <span class="stat-label">Learnings</span>
                    <span class="stat-value" id="stat-learnings"><?= $stats['total_learnings'] ?? 0 ?></span>
                </div>
            </div>
        </div>
    </header>

    <main>
        <?php if (!$has_data): ?>
        <!-- Empty State -->
        <div class="empty-state">
            <h2>No data yet</h2>
            <p>The optimizer hasn't run yet. Set up your cron job to start generating and optimizing emails.</p>
            <div class="setup-steps">
                <h3>Quick Setup</h3>
                <ol>
                    <li>Configure your <code>.env</code> file with your Claude API key and database credentials</li>
                    <li>Run <code>install.php?secret=YOUR_SECRET</code> to create database tables</li>
                    <li>Set up a cron job in Hostinger hPanel (every 10 minutes)</li>
                    <li>Or trigger manually: <code>optimizer.php?cron_secret=YOUR_SECRET</code></li>
                </ol>
            </div>
        </div>
        <?php else: ?>

        <!-- Score Trend Chart -->
        <section class="card">
            <h2>Score Trend</h2>
            <div class="chart-container">
                <canvas id="scoreTrendChart"></canvas>
            </div>
        </section>

        <!-- Two Column Layout -->
        <div class="grid-2">
            <!-- Industry Comparison -->
            <section class="card">
                <h2>Industry Performance</h2>
                <div class="chart-container">
                    <canvas id="industryChart"></canvas>
                </div>
            </section>

            <!-- Weight Evolution -->
            <section class="card">
                <h2>Weight Evolution</h2>
                <div class="chart-container">
                    <canvas id="weightChart"></canvas>
                </div>
            </section>
        </div>

        <!-- Top Emails -->
        <section class="card">
            <h2>Top Performing Emails</h2>
            <div class="filter-bar">
                <select id="industry-filter">
                    <option value="">All Industries</option>
                    <?php foreach (INDUSTRY_BENCHMARKS as $key => $b): ?>
                    <option value="<?= $key ?>"><?= htmlspecialchars($b['name']) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div id="top-emails-container">
                <table class="email-table">
                    <thead>
                        <tr>
                            <th>Score</th>
                            <th>Industry</th>
                            <th>Subject Line</th>
                            <th>Hook</th>
                            <th>Iter #</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="top-emails-body">
                        <tr><td colspan="6" class="loading">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Learnings Feed -->
        <section class="card">
            <h2>AI Learnings</h2>
            <div id="learnings-container" class="learnings-feed">
                <p class="loading">Loading...</p>
            </div>
        </section>

        <?php endif; ?>
    </main>

    <footer>
        <p>Cold Email AI Optimizer &mdash; Powered by Claude Sonnet</p>
    </footer>

    <?php if ($has_data): ?>
    <script src="assets/app.js"></script>
    <?php endif; ?>

    <!-- Email Detail Modal -->
    <div id="email-modal" class="modal hidden">
        <div class="modal-backdrop"></div>
        <div class="modal-content">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <div id="modal-body"></div>
        </div>
    </div>
</body>
</html>
