<?php
/**
 * Cold Email AI Optimizer - Main Optimization Loop
 *
 * This is the script that Hostinger's cron job runs every 10 minutes.
 * Each execution = one iteration of the optimization loop.
 *
 * Hostinger Cron Setup:
 *   Command: /usr/bin/php /home/u{YOUR_ID}/domains/{YOUR_DOMAIN}/public_html/optimizer.php cron_secret=YOUR_SECRET
 *   Interval: Every 10 minutes
 *
 * Or call via URL with secret:
 *   https://yourdomain.com/optimizer.php?cron_secret=YOUR_SECRET
 */

// Prevent browser timeout — this can take 60-90 seconds
set_time_limit(300);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';
require_once __DIR__ . '/claude_api.php';
require_once __DIR__ . '/scoring.php';
require_once __DIR__ . '/templates.php';

// --- Security: Verify cron secret ---
$secret = null;
if (php_sapi_name() === 'cli') {
    // CLI mode: parse from argv
    foreach ($argv ?? [] as $arg) {
        if (strpos($arg, 'cron_secret=') === 0) {
            $secret = substr($arg, strlen('cron_secret='));
        }
    }
} else {
    // Web mode: parse from query string
    $secret = $_GET['cron_secret'] ?? null;
}

if ($secret !== CRON_SECRET) {
    http_response_code(403);
    die('Forbidden');
}

// --- Prevent concurrent runs ---
$lock_file = __DIR__ . '/optimizer.lock';
if (file_exists($lock_file)) {
    $lock_time = (int)file_get_contents($lock_file);
    // If lock is older than 5 minutes, it's stale — remove it
    if (time() - $lock_time < 300) {
        log_message("Optimizer already running (lock exists). Skipping.");
        die('Already running');
    }
}
file_put_contents($lock_file, time());

// Cleanup lock on exit
register_shutdown_function(function() use ($lock_file) {
    @unlink($lock_file);
});

// --- Run one iteration ---
try {
    run_iteration();
} catch (Exception $e) {
    log_message("FATAL: " . $e->getMessage());
    echo "Error: " . $e->getMessage();
}

function run_iteration(): void {
    log_message("=== Starting optimization iteration ===");

    // 1. Get current state
    $iteration_num = get_last_iteration_num() + 1;
    $weights = get_latest_weights() ?? DEFAULT_WEIGHTS;

    log_message("Iteration #$iteration_num | Weights: " . json_encode($weights));

    // 2. Pick industries for this run (rotate through all 10)
    $industries = pick_industries($iteration_num, INDUSTRIES_PER_RUN);
    log_message("Industries: " . implode(', ', $industries));

    // 3. Load historical context
    $learnings = get_learnings_summary(15);
    $top_historical = get_top_emails(10);

    // 4. Generate emails for each industry
    $all_emails = [];

    foreach ($industries as $industry_key) {
        log_message("Generating emails for: $industry_key");

        if ($iteration_num === 1) {
            // First iteration: use seed templates
            $seeds = get_seed_templates();
            $emails = $seeds[$industry_key] ?? [];
            // Pad to EMAILS_PER_INDUSTRY with seeds + variations
            while (count($emails) < EMAILS_PER_INDUSTRY) {
                $emails[] = $emails[0] ?? create_fallback_email($industry_key);
            }
            $emails = array_slice($emails, 0, EMAILS_PER_INDUSTRY);
            // Tag with industry
            foreach ($emails as &$e) {
                $e['industry'] = $industry_key;
            }
            unset($e);
        } else {
            // Use Claude to generate new variations
            $emails = generate_emails($industry_key, $learnings, $top_historical, $weights);

            if (empty($emails)) {
                log_message("WARNING: Claude returned no emails for $industry_key, using seeds");
                $seeds = get_seed_templates();
                $emails = $seeds[$industry_key] ?? [create_fallback_email($industry_key)];
                foreach ($emails as &$e) {
                    $e['industry'] = $industry_key;
                }
                unset($e);
            }
        }

        // 5. Score each email deterministically
        foreach ($emails as &$email) {
            $email['scores'] = score_email($email, $weights);
        }
        unset($email);

        $all_emails = array_merge($all_emails, $emails);
    }

    if (empty($all_emails)) {
        log_message("ERROR: No emails generated. Aborting iteration.");
        return;
    }

    // 6. Sort by total score
    usort($all_emails, function($a, $b) {
        return ($b['scores']['total'] ?? 0) <=> ($a['scores']['total'] ?? 0);
    });

    $best_score = $all_emails[0]['scores']['total'] ?? 0;
    $scores = array_column(array_column($all_emails, 'scores'), 'total');
    $avg_score = count($scores) > 0 ? array_sum($scores) / count($scores) : 0;

    log_message(sprintf("Generated %d emails | Best: %.1f | Avg: %.1f", count($all_emails), $best_score, $avg_score));

    // 7. Analyze results with Claude (skip on iteration 1)
    $insights = [];
    $new_weights = $weights;

    if ($iteration_num > 1 && count($all_emails) >= 4) {
        $top = array_slice($all_emails, 0, min(5, count($all_emails)));
        $bottom = array_slice($all_emails, -min(5, count($all_emails)));

        log_message("Analyzing top vs bottom performers...");
        $insights = analyze_results($top, $bottom, $learnings);
        log_message("Insights: " . count($insights));

        // 8. Get weight adjustments from Claude
        if ($iteration_num > 2) {
            log_message("Suggesting weight adjustments...");
            $new_weights = suggest_weight_adjustments($weights, $insights, $iteration_num);
            log_message("New weights: " . json_encode($new_weights));
        }
    } else {
        $insights = ['Seed iteration — establishing baseline metrics across industries.'];
    }

    // 9. Save everything to database
    $iteration_id = save_iteration($iteration_num, $industries, $avg_score, $best_score, $insights, $new_weights);
    save_emails($iteration_id, $all_emails);
    save_learnings($iteration_id, $insights);
    save_weights($iteration_id, $new_weights);

    log_message("Iteration #$iteration_num saved. ID: $iteration_id");
    log_message("=== Iteration complete ===\n");

    // Output for cron log
    echo sprintf(
        "Iteration #%d complete. Emails: %d | Best: %.1f | Avg: %.1f\n",
        $iteration_num, count($all_emails), $best_score, $avg_score
    );
}

function create_fallback_email(string $industry_key): array {
    $benchmark = INDUSTRY_BENCHMARKS[$industry_key] ?? INDUSTRY_BENCHMARKS['saas'];
    return [
        'industry' => $industry_key,
        'subject_line' => '{first_name}, quick question?',
        'body' => "Hi {first_name}, I noticed {company} recently {recent_event}. Companies in the {$benchmark['name']} space often face {pain_point} at this stage. We helped a similar organization solve this and saw measurable results within 30 days. The approach focused on one key change that most teams overlook. Would it be worth a brief conversation to see if it applies to {company}? Open for a quick chat this week?",
        'hook_type' => 'timeline',
        'send_time' => 'Tuesday 8am',
    ];
}
