<?php
/**
 * Cold Email AI Optimizer - Configuration
 *
 * Loads environment, defines constants, and stores industry benchmarks.
 */

// Load .env file
function load_env($path = __DIR__ . '/.env') {
    if (!file_exists($path)) return;
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#') continue;
        if (strpos($line, '=') === false) continue;
        list($key, $value) = explode('=', $line, 2);
        $key = trim($key);
        $value = trim($value);
        if (!getenv($key)) {
            putenv("$key=$value");
            $_ENV[$key] = $value;
        }
    }
}

load_env();

// --- Core Settings ---
define('ANTHROPIC_API_KEY', getenv('ANTHROPIC_API_KEY') ?: '');
define('CLAUDE_MODEL', 'claude-sonnet-4-6');
define('CLAUDE_MAX_TOKENS', 4096);

define('DB_HOST', getenv('DB_HOST') ?: 'localhost');
define('DB_NAME', getenv('DB_NAME') ?: 'cold_email_optimizer');
define('DB_USER', getenv('DB_USER') ?: 'root');
define('DB_PASS', getenv('DB_PASS') ?: '');

define('CRON_SECRET', getenv('CRON_SECRET') ?: 'change-me');
define('DEBUG', (bool)(getenv('DEBUG') ?: false));

define('EMAILS_PER_INDUSTRY', 5);
define('INDUSTRIES_PER_RUN', 3);

// --- Industry Benchmarks (from 2024-2026 research data) ---
define('INDUSTRY_BENCHMARKS', [
    'saas' => [
        'name' => 'SaaS / Software',
        'avg_reply_rate' => 7.5,
        'avg_open_rate' => 38.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'scaling bottlenecks, churn reduction, integration complexity',
        'decision_makers' => 'VP Engineering, CTO, Head of Product',
    ],
    'real_estate' => [
        'name' => 'Real Estate',
        'avg_reply_rate' => 8.0,
        'avg_open_rate' => 35.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'lead generation, closing speed, market competition',
        'decision_makers' => 'Broker, Agent, Property Manager',
    ],
    'recruiting' => [
        'name' => 'Recruiting / Staffing',
        'avg_reply_rate' => 10.5,
        'avg_open_rate' => 42.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'talent shortage, time-to-fill, candidate ghosting',
        'decision_makers' => 'HR Director, Talent Acquisition Lead, CEO',
    ],
    'marketing' => [
        'name' => 'Digital Marketing / Agencies',
        'avg_reply_rate' => 3.5,
        'avg_open_rate' => 30.0,
        'best_hook' => 'problem',
        'typical_pain' => 'client acquisition, ROI proof, scaling campaigns',
        'decision_makers' => 'Marketing Director, CMO, Agency Owner',
    ],
    'consulting' => [
        'name' => 'Management Consulting',
        'avg_reply_rate' => 6.5,
        'avg_open_rate' => 33.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'pipeline development, thought leadership, client retention',
        'decision_makers' => 'Managing Partner, Principal, Director',
    ],
    'finance' => [
        'name' => 'Financial Services / Insurance',
        'avg_reply_rate' => 5.5,
        'avg_open_rate' => 28.0,
        'best_hook' => 'problem',
        'typical_pain' => 'compliance burden, client acquisition cost, digital transformation',
        'decision_makers' => 'CFO, VP Finance, Branch Manager',
    ],
    'healthcare' => [
        'name' => 'Healthcare / Medical',
        'avg_reply_rate' => 5.2,
        'avg_open_rate' => 30.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'patient acquisition, staff burnout, regulatory compliance',
        'decision_makers' => 'Practice Manager, Medical Director, Administrator',
    ],
    'legal' => [
        'name' => 'Legal Services',
        'avg_reply_rate' => 4.5,
        'avg_open_rate' => 27.0,
        'best_hook' => 'problem',
        'typical_pain' => 'client intake efficiency, billable hour pressure, competition',
        'decision_makers' => 'Managing Partner, Senior Partner, Office Manager',
    ],
    'ecommerce' => [
        'name' => 'E-commerce / Retail',
        'avg_reply_rate' => 4.0,
        'avg_open_rate' => 32.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'cart abandonment, customer acquisition cost, logistics',
        'decision_makers' => 'Ecommerce Director, Head of Growth, Founder',
    ],
    'construction' => [
        'name' => 'Construction / Trades',
        'avg_reply_rate' => 5.0,
        'avg_open_rate' => 29.0,
        'best_hook' => 'timeline',
        'typical_pain' => 'project bidding, workforce shortage, project delays',
        'decision_makers' => 'Owner, General Contractor, Operations Manager',
    ],
]);

// --- Default Scoring Weights (sum to 1.0, evolve over iterations) ---
define('DEFAULT_WEIGHTS', [
    'subject_line_quality'  => 0.20,
    'hook_type_score'       => 0.20,
    'personalization_depth' => 0.15,
    'cta_clarity'           => 0.15,
    'email_length_score'    => 0.10,
    'timing_score'          => 0.10,
    'spam_avoidance'        => 0.10,
]);

// --- Spam Trigger Words ---
define('SPAM_TRIGGERS', [
    'free', 'guarantee', 'urgent', 'act now', 'limited time', 'exclusive deal',
    'no obligation', 'risk free', 'click here', 'buy now', 'order now',
    'congratulations', 'winner', 'selected', 'claim', 'expire', 'hurry',
    'once in a lifetime', 'incredible deal', 'don\'t miss', 'special promotion',
    'zero risk', 'no cost', 'double your', 'earn extra', 'fast cash',
    'million dollars', 'cash bonus', 'credit card', 'lowest price', 'bargain',
    'discount', 'save big', 'clearance', 'no strings attached', 'apply now',
    'instant', 'amazing', 'unbelievable', '100%', 'satisfaction guaranteed',
]);

// --- Optimal Send Windows ---
define('OPTIMAL_SEND_DAYS', ['Tuesday', 'Wednesday', 'Thursday']);
define('OPTIMAL_SEND_HOURS', [6, 7, 8, 9, 10, 11]); // 6 AM - 11 AM

// --- Weight Constraints ---
define('MAX_WEIGHT', 0.35);
define('MIN_WEIGHT', 0.05);
define('MAX_WEIGHT_CHANGE_PCT', 0.05); // 5% max change per iteration
