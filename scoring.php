<?php
/**
 * Cold Email AI Optimizer - Deterministic Scoring Engine
 *
 * Scores emails on 7 dimensions (0-100 each), then computes weighted total.
 * No API calls - pure algorithmic scoring based on real-world best practices.
 */

require_once __DIR__ . '/config.php';

function score_email(array $email, array $weights): array {
    $subject = $email['subject_line'] ?? '';
    $body = $email['body'] ?? '';
    $hook_type = $email['hook_type'] ?? '';
    $send_time = $email['send_time'] ?? '';

    $scores = [
        'subject_line_quality'  => score_subject_line($subject),
        'hook_type_score'       => score_hook_type($hook_type, $body),
        'personalization_depth' => score_personalization($subject, $body),
        'cta_clarity'           => score_cta($body),
        'email_length_score'    => score_email_length($body),
        'timing_score'          => score_timing($send_time),
        'spam_avoidance'        => score_spam_triggers($subject, $body),
    ];

    // Calculate weighted total (0-100)
    $total = 0;
    foreach ($scores as $key => $value) {
        $weight = $weights[$key] ?? 0;
        $total += $value * $weight;
    }
    $scores['total'] = round($total, 2);

    return $scores;
}

function score_subject_line(string $subject): float {
    if (empty($subject)) return 0;

    $score = 0;
    $words = str_word_count($subject);

    // Optimal length: 2-4 words = max points
    if ($words >= 2 && $words <= 4) {
        $score += 40;
    } elseif ($words >= 1 && $words <= 6) {
        $score += 25;
    } elseif ($words <= 7) {
        $score += 15;
    } else {
        $score += max(0, 15 - ($words - 7) * 3);
    }

    // Personalization tokens
    $placeholders = ['{first_name}', '{company}', '{recent_event}', '{pain_point}', '{role}'];
    $found = 0;
    foreach ($placeholders as $ph) {
        if (stripos($subject, $ph) !== false) $found++;
    }
    $score += min(25, $found * 12);

    // Question format bonus
    if (substr(trim($subject), -1) === '?') {
        $score += 15;
    }

    // Lowercase start (more casual/peer-to-peer)
    if (ctype_lower($subject[0] ?? 'A')) {
        $score += 5;
    }

    // Starts with recipient reference
    if (preg_match('/^(hey|hi|quick|re:|\{first_name\})/i', $subject)) {
        $score += 10;
    }

    // Penalize all caps
    if (strtoupper($subject) === $subject && strlen($subject) > 3) {
        $score -= 20;
    }

    // Penalize excessive punctuation
    if (preg_match('/[!]{2,}|[?]{2,}/', $subject)) {
        $score -= 10;
    }

    return max(0, min(100, $score));
}

function score_hook_type(string $hook_type, string $body): float {
    $hook_type = strtolower($hook_type);

    // Base score from declared hook type
    $type_scores = [
        'timeline' => 85,      // 10.01% reply rate
        'social_proof' => 65,  // decent performer
        'curiosity' => 60,     // moderate
        'problem' => 45,       // 4.39% reply rate
    ];

    $score = $type_scores[$hook_type] ?? 30;

    // Bonus: detect timeline indicators in body
    $timeline_signals = [
        '{recent_event}', 'just saw', 'noticed you', 'congrats on',
        'saw your', 'recently', 'just read', 'your recent', 'last week',
        'this quarter', 'new role', 'funding', 'expansion', 'launched',
    ];

    $timeline_count = 0;
    foreach ($timeline_signals as $signal) {
        if (stripos($body, $signal) !== false) $timeline_count++;
    }

    if ($timeline_count >= 2) $score += 15;
    elseif ($timeline_count >= 1) $score += 8;

    return max(0, min(100, $score));
}

function score_personalization(string $subject, string $body): float {
    $combined = $subject . ' ' . $body;
    $score = 0;

    // Check for personalization placeholders
    $placeholders = [
        '{first_name}' => 15,
        '{company}' => 15,
        '{recent_event}' => 20,
        '{pain_point}' => 15,
        '{role}' => 10,
        '{industry}' => 5,
        '{city}' => 5,
    ];

    foreach ($placeholders as $ph => $points) {
        if (stripos($combined, $ph) !== false) {
            $score += $points;
        }
    }

    // Context-specific references (shows research)
    $research_signals = [
        'your team', 'your company', 'your website', 'your product',
        'your blog', 'your post', 'your talk', 'your article',
        'your linkedin', 'your podcast', 'I noticed', 'I saw that',
    ];

    $research_count = 0;
    foreach ($research_signals as $signal) {
        if (stripos($combined, $signal) !== false) $research_count++;
    }
    $score += min(20, $research_count * 7);

    return max(0, min(100, $score));
}

function score_cta(string $body): float {
    if (empty($body)) return 0;

    $score = 0;

    // Detect CTAs - look for question marks in last 2 sentences
    $sentences = preg_split('/[.!?]+/', $body, -1, PREG_SPLIT_NO_EMPTY);
    $sentences = array_map('trim', $sentences);
    $sentences = array_filter($sentences);
    $sentences = array_values($sentences);

    $last_sentences = array_slice($sentences, -2);
    $has_question_cta = false;
    $cta_text = '';

    foreach ($last_sentences as $s) {
        // Check if it's a CTA-like question
        if (preg_match('/(open|interested|worth|mind|want|chat|call|meet|talk|time|free|available|grab|schedule|book)/i', $s)) {
            $has_question_cta = true;
            $cta_text = $s;
            break;
        }
    }

    // Has a CTA at all
    if ($has_question_cta) {
        $score += 40;
    } else {
        // Check for imperative CTAs
        $imperative_ctas = ['let me know', 'reply', 'click', 'check out', 'visit', 'sign up', 'book a'];
        foreach ($imperative_ctas as $cta) {
            if (stripos($body, $cta) !== false) {
                $score += 25;
                $cta_text = $cta;
                break;
            }
        }
    }

    // CTA brevity (under 6 words)
    if ($cta_text) {
        $cta_words = str_word_count($cta_text);
        if ($cta_words <= 6) {
            $score += 30;
        } elseif ($cta_words <= 10) {
            $score += 15;
        }
    }

    // Single CTA (penalize multiple)
    $cta_patterns = ['?', 'let me know', 'click', 'book', 'schedule', 'sign up', 'register'];
    $cta_count = 0;
    foreach ($cta_patterns as $p) {
        $cta_count += substr_count(strtolower($body), $p);
    }
    if ($cta_count === 1) {
        $score += 20; // Single CTA - perfect
    } elseif ($cta_count === 2) {
        $score += 10; // Acceptable
    }
    // 3+ CTAs = no bonus (decision paralysis)

    // Specific time mention bonus
    if (preg_match('/(monday|tuesday|wednesday|thursday|friday|this week|next week|tomorrow)/i', $body)) {
        $score += 10;
    }

    return max(0, min(100, $score));
}

function score_email_length(string $body): float {
    if (empty($body)) return 0;

    // Count sentences
    $sentences = preg_split('/[.!?]+/', $body, -1, PREG_SPLIT_NO_EMPTY);
    $sentences = array_filter(array_map('trim', $sentences));
    $count = count($sentences);

    // Optimal: 6-8 sentences = 100
    if ($count >= 6 && $count <= 8) {
        return 100;
    }

    // Penalty per sentence away from optimal range
    if ($count < 6) {
        $distance = 6 - $count;
        return max(0, 100 - ($distance * 20));
    }

    // Too long
    $distance = $count - 8;
    return max(0, 100 - ($distance * 15));
}

function score_timing(string $send_time): float {
    if (empty($send_time)) return 50; // Default middle score

    $send_time = strtolower($send_time);
    $score = 0;

    // Check day
    $optimal_days = ['tuesday', 'wednesday', 'thursday'];
    $good_days = ['monday', 'friday'];

    foreach ($optimal_days as $day) {
        if (strpos($send_time, $day) !== false) {
            $score += 60;
            break;
        }
    }
    if ($score === 0) {
        foreach ($good_days as $day) {
            if (strpos($send_time, $day) !== false) {
                $score += 35;
                break;
            }
        }
    }

    // Check hour
    if (preg_match('/(\d{1,2})\s*(am|pm)/i', $send_time, $m)) {
        $hour = (int)$m[1];
        $period = strtolower($m[2]);
        if ($period === 'pm' && $hour !== 12) $hour += 12;
        if ($period === 'am' && $hour === 12) $hour = 0;

        // Optimal: 6-11 AM
        if ($hour >= 6 && $hour <= 11) {
            $score += 40;
        } elseif ($hour >= 12 && $hour <= 14) {
            $score += 25; // Acceptable afternoon
        } else {
            $score += 10;
        }
    } else {
        $score += 20; // Time not specified clearly
    }

    return max(0, min(100, $score));
}

function score_spam_triggers(string $subject, string $body): float {
    $combined = strtolower($subject . ' ' . $body);
    $score = 100;

    foreach (SPAM_TRIGGERS as $trigger) {
        $trigger_lower = strtolower($trigger);
        $occurrences = substr_count($combined, $trigger_lower);
        if ($occurrences > 0) {
            $score -= $occurrences * 12;
        }
    }

    // Bonus for clean, professional language
    $professional_signals = ['appreciate', 'thank you', 'regards', 'best', 'cheers'];
    foreach ($professional_signals as $sig) {
        if (strpos($combined, $sig) !== false) {
            $score += 3;
        }
    }

    // Penalize excessive caps in body
    $caps_ratio = preg_match_all('/[A-Z]/', $body) / max(1, strlen($body));
    if ($caps_ratio > 0.15) {
        $score -= 15;
    }

    // Penalize excessive exclamation marks
    $excl_count = substr_count($combined, '!');
    if ($excl_count > 1) {
        $score -= ($excl_count - 1) * 8;
    }

    return max(0, min(100, $score));
}
