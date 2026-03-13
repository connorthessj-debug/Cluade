<?php
/**
 * Cold Email AI Optimizer - Single Iteration Runner
 *
 * Runs ONE optimization iteration. Used by:
 *   - start.php (calls run_iteration() directly for the continuous loop)
 *   - Cron jobs: php optimizer.php cron_secret=YOUR_SECRET
 *   - Browser:   optimizer.php?cron_secret=YOUR_SECRET
 *
 * For continuous local running, use start.php instead.
 */

set_time_limit(300);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';
require_once __DIR__ . '/claude_api.php';
require_once __DIR__ . '/scoring.php';
require_once __DIR__ . '/templates.php';

// Only run directly if called as main script (not included by start.php)
if (realpath(__FILE__) === realpath($_SERVER['SCRIPT_FILENAME'] ?? '')) {

    // Security: Verify cron secret
    $secret = null;
    if (php_sapi_name() === 'cli') {
        foreach ($argv ?? [] as $arg) {
            if (strpos($arg, 'cron_secret=') === 0) {
                $secret = substr($arg, strlen('cron_secret='));
            }
        }
    } else {
        $secret = $_GET['cron_secret'] ?? null;
    }

    if ($secret !== CRON_SECRET) {
        http_response_code(403);
        die('Forbidden');
    }

    // Prevent concurrent runs
    $lock_file = __DIR__ . '/data/optimizer.lock';
    $data_dir = dirname($lock_file);
    if (!is_dir($data_dir)) mkdir($data_dir, 0755, true);

    if (file_exists($lock_file)) {
        $lock_time = (int)file_get_contents($lock_file);
        if (time() - $lock_time < 300) {
            log_message("Optimizer already running (lock exists). Skipping.");
            die('Already running');
        }
    }
    file_put_contents($lock_file, time());
    register_shutdown_function(function() use ($lock_file) { @unlink($lock_file); });

    // Run
    try {
        create_tables();
        $iteration_num = get_last_iteration_num() + 1;
        run_optimizer_iteration($iteration_num);
        echo "Iteration #$iteration_num complete.\n";
    } catch (Exception $e) {
        log_message("FATAL: " . $e->getMessage());
        echo "Error: " . $e->getMessage() . "\n";
    }
}

/**
 * Execute a single optimization iteration.
 */
function run_optimizer_iteration(int $iteration_num): array {
    log_message("=== Starting iteration #$iteration_num ===");

    $weights = get_latest_weights() ?? DEFAULT_WEIGHTS;
    $industries = pick_industries($iteration_num, INDUSTRIES_PER_RUN);
    $learnings = get_learnings_summary(15);
    $top_historical = get_top_emails(10);

    $all_emails = [];

    foreach ($industries as $industry_key) {
        if ($iteration_num === 1) {
            $seeds = get_seed_templates();
            $emails = $seeds[$industry_key] ?? [];
            while (count($emails) < EMAILS_PER_INDUSTRY) {
                $emails[] = $emails[0] ?? create_optimizer_fallback($industry_key);
            }
            $emails = array_slice($emails, 0, EMAILS_PER_INDUSTRY);
            foreach ($emails as &$e) { $e['industry'] = $industry_key; }
            unset($e);
        } else {
            $emails = generate_emails($industry_key, $learnings, $top_historical, $weights);
            if (empty($emails)) {
                $seeds = get_seed_templates();
                $emails = $seeds[$industry_key] ?? [create_optimizer_fallback($industry_key)];
                foreach ($emails as &$e) { $e['industry'] = $industry_key; }
                unset($e);
            }
        }

        foreach ($emails as &$email) {
            $email['scores'] = score_email($email, $weights);
        }
        unset($email);

        $all_emails = array_merge($all_emails, $emails);
    }

    if (empty($all_emails)) {
        log_message("No emails generated for iteration #$iteration_num");
        return ['error' => 'No emails generated'];
    }

    usort($all_emails, fn($a, $b) => ($b['scores']['total'] ?? 0) <=> ($a['scores']['total'] ?? 0));

    $best_score = $all_emails[0]['scores']['total'] ?? 0;
    $score_values = array_column(array_column($all_emails, 'scores'), 'total');
    $avg_score = count($score_values) > 0 ? array_sum($score_values) / count($score_values) : 0;

    $insights = [];
    $new_weights = $weights;

    if ($iteration_num > 1 && count($all_emails) >= 4) {
        $top = array_slice($all_emails, 0, 5);
        $bottom = array_slice($all_emails, -5);
        $insights = analyze_results($top, $bottom, $learnings);

        if ($iteration_num > 2) {
            $new_weights = suggest_weight_adjustments($weights, $insights, $iteration_num);
        }
    } else {
        $insights = ['Seed iteration — establishing baseline metrics across industries.'];
    }

    $iteration_id = save_iteration($iteration_num, $industries, $avg_score, $best_score, $insights, $new_weights);
    save_emails($iteration_id, $all_emails);
    save_learnings($iteration_id, $insights);
    save_weights($iteration_id, $new_weights);

    log_message("Iteration #$iteration_num done. Best: $best_score, Avg: $avg_score");

    return [
        'iteration_num' => $iteration_num,
        'emails_count' => count($all_emails),
        'best_score' => $best_score,
        'avg_score' => $avg_score,
        'insights' => $insights,
    ];
}

function create_optimizer_fallback(string $industry_key): array {
    $benchmark = INDUSTRY_BENCHMARKS[$industry_key] ?? INDUSTRY_BENCHMARKS['saas'];
    return [
        'industry' => $industry_key,
        'subject_line' => '{first_name}, quick question?',
        'body' => "Hi {first_name}, I noticed {company} recently {recent_event}. Companies in the {$benchmark['name']} space often face {pain_point} at this stage. We helped a similar organization solve this and saw measurable results within 30 days. The approach focused on one key change that most teams overlook. Would it be worth a brief conversation to see if it applies to {company}? Open for a quick chat this week?",
        'hook_type' => 'timeline',
        'send_time' => 'Tuesday 8am',
    ];
}
