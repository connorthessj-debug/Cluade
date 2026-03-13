<?php
/**
 * Cold Email AI Optimizer - Local Runner
 *
 * Starts the optimization loop and dashboard server locally.
 *
 * Usage:
 *   php start.php              # Run optimizer loop + launch dashboard
 *   php start.php --once       # Run a single iteration then exit
 *   php start.php --dashboard  # Launch dashboard only (no optimizer)
 *   php start.php --loop       # Run optimizer loop only (no dashboard)
 */

set_time_limit(0);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';
require_once __DIR__ . '/claude_api.php';
require_once __DIR__ . '/scoring.php';
require_once __DIR__ . '/templates.php';

// --- Parse CLI arguments ---
$mode = 'full'; // full, once, dashboard, loop
foreach ($argv ?? [] as $arg) {
    if ($arg === '--once') $mode = 'once';
    if ($arg === '--dashboard') $mode = 'dashboard';
    if ($arg === '--loop') $mode = 'loop';
}

// --- Ensure database exists ---
create_tables();

// --- Banner ---
echo "\n";
echo "  ┌─────────────────────────────────────────┐\n";
echo "  │     Cold Email AI Optimizer v1.0         │\n";
echo "  │     Self-improving email generation      │\n";
echo "  └─────────────────────────────────────────┘\n\n";

$last_iter = get_last_iteration_num();
echo "  Mode: $mode\n";
echo "  Last iteration: #$last_iter\n";
echo "  Loop interval: " . LOOP_INTERVAL . "s\n";
echo "  Model: " . CLAUDE_MODEL . "\n\n";

// --- Launch dashboard in background ---
$dashboard_proc = null;

if ($mode === 'full' || $mode === 'dashboard') {
    $port = DASHBOARD_PORT;
    $docroot = __DIR__;

    echo "  Starting dashboard at http://localhost:$port ...\n";

    // Use PHP's built-in web server
    $cmd = sprintf(
        'php -S localhost:%d -t %s > /dev/null 2>&1 & echo $!',
        $port,
        escapeshellarg($docroot)
    );

    $pid = trim(shell_exec($cmd));

    if ($pid && is_numeric($pid)) {
        $dashboard_proc = (int)$pid;
        echo "  Dashboard running (PID: $dashboard_proc)\n";
        echo "  Open: http://localhost:$port\n\n";
    } else {
        echo "  WARNING: Could not start dashboard server.\n";
        echo "  You can start it manually: php -S localhost:$port -t $docroot\n\n";
    }

    // Cleanup dashboard on exit
    if ($dashboard_proc) {
        register_shutdown_function(function() use ($dashboard_proc) {
            echo "\n  Stopping dashboard (PID: $dashboard_proc)...\n";
            if (PHP_OS_FAMILY === 'Windows') {
                exec("taskkill /PID $dashboard_proc /F 2>NUL");
            } else {
                exec("kill $dashboard_proc 2>/dev/null");
            }
        });
    }

    if ($mode === 'dashboard') {
        echo "  Dashboard-only mode. Press Ctrl+C to stop.\n";
        while (true) { sleep(60); }
    }
}

// --- Handle Ctrl+C gracefully ---
if (function_exists('pcntl_signal')) {
    pcntl_signal(SIGINT, function() {
        echo "\n\n  Shutting down gracefully...\n";
        exit(0);
    });
    pcntl_signal(SIGTERM, function() {
        echo "\n\n  Shutting down gracefully...\n";
        exit(0);
    });
}

// --- Optimization loop ---
if ($mode === 'full' || $mode === 'loop' || $mode === 'once') {
    $iteration_num = get_last_iteration_num() + 1;

    while (true) {
        if (function_exists('pcntl_signal_dispatch')) {
            pcntl_signal_dispatch();
        }

        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        echo "  ITERATION #$iteration_num\n";
        echo "  " . date('Y-m-d H:i:s') . "\n";
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n";

        try {
            run_single_iteration($iteration_num);
            $iteration_num++;
        } catch (Exception $e) {
            echo "  ERROR: " . $e->getMessage() . "\n\n";
            log_message("Iteration $iteration_num FAILED: " . $e->getMessage());
        }

        if ($mode === 'once') {
            echo "  Single iteration complete. Exiting.\n\n";
            break;
        }

        $interval = LOOP_INTERVAL;
        echo "  Next iteration in " . format_duration($interval) . "...\n";
        echo "  (Press Ctrl+C to stop)\n\n";

        // Sleep in small chunks so Ctrl+C is responsive
        $slept = 0;
        while ($slept < $interval) {
            if (function_exists('pcntl_signal_dispatch')) {
                pcntl_signal_dispatch();
            }
            sleep(min(5, $interval - $slept));
            $slept += 5;
        }
    }
}

// === Core Iteration Logic ===

function run_single_iteration(int $iteration_num): void {
    // 1. Load weights
    $weights = get_latest_weights() ?? DEFAULT_WEIGHTS;
    echo "  Weights loaded";
    if ($iteration_num > 1) {
        $top_weight = '';
        $top_val = 0;
        foreach ($weights as $k => $v) {
            if ($v > $top_val) { $top_val = $v; $top_weight = $k; }
        }
        echo " (top: $top_weight @ " . round($top_val * 100) . "%)";
    }
    echo "\n";

    // 2. Pick industries
    $industries = pick_industries($iteration_num, INDUSTRIES_PER_RUN);
    $industry_names = array_map(fn($k) => INDUSTRY_BENCHMARKS[$k]['name'] ?? $k, $industries);
    echo "  Industries: " . implode(', ', $industry_names) . "\n";

    // 3. Load history
    $learnings = get_learnings_summary(15);
    $top_historical = get_top_emails(10);

    // 4. Generate emails
    $all_emails = [];

    foreach ($industries as $industry_key) {
        echo "  Generating for $industry_key... ";

        if ($iteration_num === 1) {
            $seeds = get_seed_templates();
            $emails = $seeds[$industry_key] ?? [];
            while (count($emails) < EMAILS_PER_INDUSTRY) {
                $emails[] = $emails[0] ?? create_fallback_email($industry_key);
            }
            $emails = array_slice($emails, 0, EMAILS_PER_INDUSTRY);
            foreach ($emails as &$e) { $e['industry'] = $industry_key; }
            unset($e);
            echo count($emails) . " seeds\n";
        } else {
            $emails = generate_emails($industry_key, $learnings, $top_historical, $weights);
            if (empty($emails)) {
                echo "API failed, using seeds\n";
                $seeds = get_seed_templates();
                $emails = $seeds[$industry_key] ?? [create_fallback_email($industry_key)];
                foreach ($emails as &$e) { $e['industry'] = $industry_key; }
                unset($e);
            } else {
                echo count($emails) . " generated\n";
            }
        }

        // Score
        foreach ($emails as &$email) {
            $email['scores'] = score_email($email, $weights);
        }
        unset($email);

        $all_emails = array_merge($all_emails, $emails);
    }

    if (empty($all_emails)) {
        echo "  No emails generated. Skipping.\n";
        return;
    }

    // 5. Sort
    usort($all_emails, fn($a, $b) => ($b['scores']['total'] ?? 0) <=> ($a['scores']['total'] ?? 0));

    $best_score = $all_emails[0]['scores']['total'] ?? 0;
    $scores = array_column(array_column($all_emails, 'scores'), 'total');
    $avg_score = count($scores) > 0 ? array_sum($scores) / count($scores) : 0;

    echo "\n  Results: " . count($all_emails) . " emails\n";
    echo "  Best:  " . number_format($best_score, 1) . "/100\n";
    echo "  Avg:   " . number_format($avg_score, 1) . "/100\n";

    // Show top email preview
    $top_email = $all_emails[0];
    echo "\n  Top email:\n";
    echo "  Subject: " . $top_email['subject_line'] . "\n";
    echo "  Hook:    " . $top_email['hook_type'] . " | Industry: " . $top_email['industry'] . "\n";

    // 6. Analyze with Claude
    $insights = [];
    $new_weights = $weights;

    if ($iteration_num > 1 && count($all_emails) >= 4) {
        echo "\n  Analyzing results with Claude... ";
        $top = array_slice($all_emails, 0, 5);
        $bottom = array_slice($all_emails, -5);
        $insights = analyze_results($top, $bottom, $learnings);
        echo count($insights) . " insights\n";

        foreach ($insights as $i => $insight) {
            echo "    " . ($i + 1) . ". $insight\n";
        }

        // 7. Weight adjustments
        if ($iteration_num > 2) {
            echo "\n  Adjusting weights... ";
            $new_weights = suggest_weight_adjustments($weights, $insights, $iteration_num);

            // Show changes
            $changes = [];
            foreach ($new_weights as $k => $v) {
                $old = $weights[$k] ?? 0;
                $diff = $v - $old;
                if (abs($diff) > 0.0001) {
                    $sign = $diff > 0 ? '+' : '';
                    $changes[] = "$k: $sign" . round($diff * 100, 1) . "%";
                }
            }
            echo (empty($changes) ? 'no changes' : implode(', ', $changes)) . "\n";
        }
    } else {
        $insights = ['Seed iteration — establishing baseline metrics across industries.'];
        echo "\n  Seed iteration (analysis starts at iteration #2)\n";
    }

    // 8. Save
    $iteration_id = save_iteration($iteration_num, $industries, $avg_score, $best_score, $insights, $new_weights);
    save_emails($iteration_id, $all_emails);
    save_learnings($iteration_id, $insights);
    save_weights($iteration_id, $new_weights);

    echo "\n  Saved to database (iteration ID: $iteration_id)\n";
    log_message("Iteration #$iteration_num complete. Best: $best_score, Avg: $avg_score");
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

function format_duration(int $seconds): string {
    if ($seconds < 60) return "{$seconds}s";
    $min = floor($seconds / 60);
    $sec = $seconds % 60;
    return $sec > 0 ? "{$min}m {$sec}s" : "{$min}m";
}
