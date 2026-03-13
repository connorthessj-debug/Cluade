<?php
/**
 * Cold Email AI Optimizer - Claude API Client
 *
 * Raw cURL calls to the Anthropic Messages API. No SDK required.
 */

require_once __DIR__ . '/config.php';

function claude_request(string $system_prompt, string $user_prompt): ?string {
    $url = 'https://api.anthropic.com/v1/messages';

    $payload = json_encode([
        'model' => CLAUDE_MODEL,
        'max_tokens' => CLAUDE_MAX_TOKENS,
        'system' => $system_prompt,
        'messages' => [
            ['role' => 'user', 'content' => $user_prompt],
        ],
    ]);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $payload,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'x-api-key: ' . ANTHROPIC_API_KEY,
            'anthropic-version: 2023-06-01',
        ],
        CURLOPT_TIMEOUT => 120,
        CURLOPT_CONNECTTIMEOUT => 30,
    ]);

    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);

    if ($error) {
        log_message("Claude API curl error: $error");
        return null;
    }

    if ($http_code !== 200) {
        log_message("Claude API HTTP $http_code: $response");
        return null;
    }

    $data = json_decode($response, true);
    if (!$data || empty($data['content'][0]['text'])) {
        log_message("Claude API unexpected response: $response");
        return null;
    }

    return $data['content'][0]['text'];
}

function generate_emails(string $industry_key, array $learnings, array $top_examples, array $weights): array {
    $benchmark = INDUSTRY_BENCHMARKS[$industry_key] ?? null;
    if (!$benchmark) return [];

    $system = build_generation_system_prompt($benchmark, $weights);
    $user = build_generation_user_prompt($industry_key, $benchmark, $learnings, $top_examples);

    $response = claude_request($system, $user);
    if (!$response) return [];

    return parse_email_response($response, $industry_key);
}

function build_generation_system_prompt(array $benchmark, array $weights): string {
    $weights_str = '';
    foreach ($weights as $k => $v) {
        $weights_str .= "  - $k: " . round($v * 100) . "%\n";
    }

    return <<<PROMPT
You are an expert cold email copywriter and optimization engine. Your job is to generate high-performing cold email variations.

INDUSTRY CONTEXT:
- Industry: {$benchmark['name']}
- Average reply rate: {$benchmark['avg_reply_rate']}%
- Average open rate: {$benchmark['avg_open_rate']}%
- Best hook type: {$benchmark['best_hook']}
- Common pain points: {$benchmark['typical_pain']}
- Decision makers: {$benchmark['decision_makers']}

SCORING CRITERIA (current weights):
$weights_str

KEY RULES FOR HIGH-SCORING EMAILS:
1. Subject lines: 2-4 words, personalized, question format scores highest
2. Hook types: Timeline-based hooks (referencing recent events) score 2.3x higher than problem-statement hooks
3. Personalization: Use {first_name}, {company}, {recent_event}, {pain_point} placeholders
4. Length: Exactly 6-8 sentences. Not more, not less.
5. CTA: Single call-to-action, under 6 words, specific (e.g. "Open for a quick chat Tuesday?")
6. Avoid spam triggers: Never use words like "free", "guarantee", "urgent", "act now", "limited time"
7. Tone: Conversational, peer-to-peer, not salesy

You MUST respond with ONLY a JSON array of exactly 5 email objects. No markdown, no explanation.
Each object must have these exact keys: subject_line, body, hook_type, send_time
- hook_type must be one of: "timeline", "problem", "social_proof", "curiosity"
- send_time must be a specific day and hour, e.g. "Tuesday 8am"
PROMPT;
}

function build_generation_user_prompt(string $industry_key, array $benchmark, array $learnings, array $top_examples): string {
    $prompt = "Generate 5 cold email variations for the {$benchmark['name']} industry.\n\n";

    if (!empty($learnings)) {
        $prompt .= "LEARNINGS FROM PREVIOUS ITERATIONS (apply these):\n";
        $recent = array_slice($learnings, 0, 10);
        foreach ($recent as $l) {
            $prompt .= "- {$l['insight']}\n";
        }
        $prompt .= "\n";
    }

    if (!empty($top_examples)) {
        $prompt .= "TOP PERFORMING EMAILS TO LEARN FROM:\n";
        $shown = array_slice($top_examples, 0, 3);
        foreach ($shown as $ex) {
            $prompt .= "---\nSubject: {$ex['subject_line']}\nBody: {$ex['body']}\nScore: {$ex['total_score']}/100\nIndustry: {$ex['industry']}\n";
        }
        $prompt .= "---\n\n";
    }

    $prompt .= "Remember: Return ONLY a valid JSON array of 5 email objects. No markdown code fences.";
    return $prompt;
}

function analyze_results(array $top_emails, array $bottom_emails, array $history): array {
    $system = <<<PROMPT
You are a cold email optimization analyst. Compare top-performing and bottom-performing emails to extract actionable insights.

Focus on:
1. What patterns make top emails score higher?
2. What mistakes do bottom emails make?
3. Which specific changes would improve future emails?
4. Any cross-industry patterns worth noting?

Respond with ONLY a JSON array of insight strings. Each insight should be 1-2 sentences and actionable.
Return exactly 5 insights. No markdown, no explanation.
PROMPT;

    $user = "TOP PERFORMERS (highest scores):\n";
    foreach (array_slice($top_emails, 0, 5) as $e) {
        $user .= sprintf(
            "---\nIndustry: %s | Score: %.1f | Subject: %s\nBody: %s\nHook: %s\n",
            $e['industry'], $e['scores']['total'] ?? $e['total_score'] ?? 0,
            $e['subject_line'], $e['body'], $e['hook_type']
        );
    }

    $user .= "\nBOTTOM PERFORMERS (lowest scores):\n";
    foreach (array_slice($bottom_emails, 0, 5) as $e) {
        $user .= sprintf(
            "---\nIndustry: %s | Score: %.1f | Subject: %s\nBody: %s\nHook: %s\n",
            $e['industry'], $e['scores']['total'] ?? $e['total_score'] ?? 0,
            $e['subject_line'], $e['body'], $e['hook_type']
        );
    }

    if (!empty($history)) {
        $user .= "\nPREVIOUS INSIGHTS (for context, don't repeat these):\n";
        foreach (array_slice($history, 0, 5) as $h) {
            $user .= "- {$h['insight']}\n";
        }
    }

    $user .= "\nReturn ONLY a JSON array of 5 new insight strings.";

    $response = claude_request($system, $user);
    if (!$response) return ['Analysis failed - will retry next iteration'];

    return parse_json_array($response) ?: ['Analysis produced no parseable insights'];
}

function suggest_weight_adjustments(array $current_weights, array $insights, int $iteration_num): array {
    $weights_json = json_encode($current_weights, JSON_PRETTY_PRINT);
    $insights_str = implode("\n", array_map(fn($i) => "- $i", $insights));

    $system = <<<PROMPT
You are a scoring weight optimization engine. Based on iteration insights, suggest adjustments to email scoring weights.

RULES:
1. Each weight change must be at most +/- 5% of its current value (e.g., 0.20 can become 0.19-0.21)
2. All weights must sum to exactly 1.0
3. No weight can exceed 0.35 or go below 0.05
4. Changes must be justified by the insights
5. In early iterations (< 5), make smaller changes. In later iterations, be more decisive.

Respond with ONLY a JSON object with these exact keys and numeric values:
subject_line_quality, hook_type_score, personalization_depth, cta_clarity, email_length_score, timing_score, spam_avoidance

No explanation, no markdown. Just the JSON object.
PROMPT;

    $user = "Current iteration: $iteration_num\n\nCurrent weights:\n$weights_json\n\nInsights from this iteration:\n$insights_str\n\nReturn the adjusted weights as a JSON object.";

    $response = claude_request($system, $user);
    if (!$response) return $current_weights;

    $new_weights = parse_json_object($response);
    if (!$new_weights) return $current_weights;

    return enforce_weight_constraints($current_weights, $new_weights);
}

function enforce_weight_constraints(array $old, array $new): array {
    $keys = array_keys(DEFAULT_WEIGHTS);
    $result = [];

    foreach ($keys as $key) {
        $old_val = $old[$key] ?? DEFAULT_WEIGHTS[$key];
        $new_val = $new[$key] ?? $old_val;

        // Enforce max change of 5%
        $max_change = $old_val * MAX_WEIGHT_CHANGE_PCT;
        $new_val = max($old_val - $max_change, min($old_val + $max_change, $new_val));

        // Enforce bounds
        $new_val = max(MIN_WEIGHT, min(MAX_WEIGHT, $new_val));

        $result[$key] = $new_val;
    }

    // Normalize to sum to 1.0
    $sum = array_sum($result);
    if ($sum > 0) {
        foreach ($result as $k => $v) {
            $result[$k] = round($v / $sum, 4);
        }
    }

    return $result;
}

function parse_email_response(string $response, string $industry_key): array {
    $emails = parse_json_array($response);
    if (!$emails) return [];

    $result = [];
    foreach ($emails as $email) {
        if (!is_array($email)) continue;
        if (empty($email['subject_line']) || empty($email['body'])) continue;

        $result[] = [
            'industry' => $industry_key,
            'subject_line' => $email['subject_line'],
            'body' => $email['body'],
            'hook_type' => $email['hook_type'] ?? 'unknown',
            'send_time' => $email['send_time'] ?? 'Tuesday 8am',
        ];
    }
    return $result;
}

function parse_json_array(string $text): ?array {
    $text = trim($text);
    // Strip markdown code fences if present
    $text = preg_replace('/^```(?:json)?\s*/i', '', $text);
    $text = preg_replace('/\s*```$/', '', $text);
    $text = trim($text);

    $data = json_decode($text, true);
    if (is_array($data) && !empty($data)) return $data;

    // Try to find JSON array in the text
    if (preg_match('/\[[\s\S]*\]/', $text, $matches)) {
        $data = json_decode($matches[0], true);
        if (is_array($data)) return $data;
    }

    return null;
}

function parse_json_object(string $text): ?array {
    $text = trim($text);
    $text = preg_replace('/^```(?:json)?\s*/i', '', $text);
    $text = preg_replace('/\s*```$/', '', $text);
    $text = trim($text);

    $data = json_decode($text, true);
    if (is_array($data) && !empty($data)) return $data;

    // Try to find JSON object in the text
    if (preg_match('/\{[\s\S]*\}/', $text, $matches)) {
        $data = json_decode($matches[0], true);
        if (is_array($data)) return $data;
    }

    return null;
}

function log_message(string $msg): void {
    $timestamp = date('Y-m-d H:i:s');
    $line = "[$timestamp] $msg\n";
    if (DEBUG) {
        echo $line;
    }
    @file_put_contents(__DIR__ . '/optimizer.log', $line, FILE_APPEND | LOCK_EX);
}
