<?php
/**
 * Cold Email AI Optimizer - Database Layer
 *
 * SQLite operations — zero config, runs anywhere PHP runs.
 * Database file stored at data/optimizer.db
 */

require_once __DIR__ . '/config.php';

function get_db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $db_path = DB_PATH;
        $dir = dirname($db_path);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        $pdo = new PDO('sqlite:' . $db_path, null, null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $pdo->exec('PRAGMA journal_mode=WAL');
        $pdo->exec('PRAGMA foreign_keys=ON');
    }
    return $pdo;
}

function create_tables(): void {
    $db = get_db();

    $db->exec("
        CREATE TABLE IF NOT EXISTS iterations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_num INTEGER NOT NULL UNIQUE,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            industries TEXT NOT NULL,
            avg_score REAL DEFAULT 0,
            best_score REAL DEFAULT 0,
            insights TEXT,
            weight_snapshot TEXT
        )
    ");

    $db->exec("
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_id INTEGER NOT NULL REFERENCES iterations(id) ON DELETE CASCADE,
            industry TEXT NOT NULL,
            subject_line TEXT,
            body TEXT,
            hook_type TEXT,
            send_time TEXT,
            total_score REAL DEFAULT 0,
            subject_score REAL DEFAULT 0,
            hook_score REAL DEFAULT 0,
            personalization_score REAL DEFAULT 0,
            cta_score REAL DEFAULT 0,
            length_score REAL DEFAULT 0,
            timing_score REAL DEFAULT 0,
            spam_score REAL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");

    $db->exec("CREATE INDEX IF NOT EXISTS idx_emails_industry ON emails(industry)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_emails_score ON emails(total_score DESC)");

    $db->exec("
        CREATE TABLE IF NOT EXISTS learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_id INTEGER NOT NULL REFERENCES iterations(id) ON DELETE CASCADE,
            insight TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");

    $db->exec("
        CREATE TABLE IF NOT EXISTS weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_id INTEGER NOT NULL REFERENCES iterations(id) ON DELETE CASCADE,
            subject_line_quality REAL NOT NULL,
            hook_type_score REAL NOT NULL,
            personalization_depth REAL NOT NULL,
            cta_clarity REAL NOT NULL,
            email_length_score REAL NOT NULL,
            timing_score REAL NOT NULL,
            spam_avoidance REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");
}

function get_last_iteration_num(): int {
    $db = get_db();
    $stmt = $db->query("SELECT MAX(iteration_num) as num FROM iterations");
    $row = $stmt->fetch();
    return (int)($row['num'] ?? 0);
}

function save_iteration(int $iter_num, array $industries, float $avg_score, float $best_score, array $insights, array $weights): int {
    $db = get_db();
    $stmt = $db->prepare("
        INSERT INTO iterations (iteration_num, industries, avg_score, best_score, insights, weight_snapshot)
        VALUES (?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $iter_num,
        json_encode($industries),
        $avg_score,
        $best_score,
        json_encode($insights),
        json_encode($weights),
    ]);
    return (int)$db->lastInsertId();
}

function save_email(int $iteration_id, array $email): void {
    $db = get_db();
    $stmt = $db->prepare("
        INSERT INTO emails (iteration_id, industry, subject_line, body, hook_type, send_time,
            total_score, subject_score, hook_score, personalization_score,
            cta_score, length_score, timing_score, spam_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $scores = $email['scores'] ?? [];
    $stmt->execute([
        $iteration_id,
        $email['industry'] ?? '',
        $email['subject_line'] ?? '',
        $email['body'] ?? '',
        $email['hook_type'] ?? '',
        $email['send_time'] ?? '',
        $scores['total'] ?? 0,
        $scores['subject_line_quality'] ?? 0,
        $scores['hook_type_score'] ?? 0,
        $scores['personalization_depth'] ?? 0,
        $scores['cta_clarity'] ?? 0,
        $scores['email_length_score'] ?? 0,
        $scores['timing_score'] ?? 0,
        $scores['spam_avoidance'] ?? 0,
    ]);
}

function save_emails(int $iteration_id, array $emails): void {
    foreach ($emails as $email) {
        save_email($iteration_id, $email);
    }
}

function save_learnings(int $iteration_id, array $insights): void {
    $db = get_db();
    $stmt = $db->prepare("INSERT INTO learnings (iteration_id, insight) VALUES (?, ?)");
    foreach ($insights as $insight) {
        $stmt->execute([$iteration_id, $insight]);
    }
}

function save_weights(int $iteration_id, array $weights): void {
    $db = get_db();
    $stmt = $db->prepare("
        INSERT INTO weights (iteration_id, subject_line_quality, hook_type_score,
            personalization_depth, cta_clarity, email_length_score, timing_score, spam_avoidance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $iteration_id,
        $weights['subject_line_quality'],
        $weights['hook_type_score'],
        $weights['personalization_depth'],
        $weights['cta_clarity'],
        $weights['email_length_score'],
        $weights['timing_score'],
        $weights['spam_avoidance'],
    ]);
}

function get_latest_weights(): ?array {
    $db = get_db();
    $stmt = $db->query("SELECT * FROM weights ORDER BY id DESC LIMIT 1");
    $row = $stmt->fetch();
    if (!$row) return null;
    return [
        'subject_line_quality'  => (float)$row['subject_line_quality'],
        'hook_type_score'       => (float)$row['hook_type_score'],
        'personalization_depth' => (float)$row['personalization_depth'],
        'cta_clarity'           => (float)$row['cta_clarity'],
        'email_length_score'    => (float)$row['email_length_score'],
        'timing_score'          => (float)$row['timing_score'],
        'spam_avoidance'        => (float)$row['spam_avoidance'],
    ];
}

function get_top_emails(int $limit = 10): array {
    $db = get_db();
    $stmt = $db->prepare("
        SELECT e.*, i.iteration_num
        FROM emails e
        JOIN iterations i ON e.iteration_id = i.id
        ORDER BY e.total_score DESC
        LIMIT ?
    ");
    $stmt->execute([$limit]);
    return $stmt->fetchAll();
}

function get_top_emails_for_industry(string $industry, int $limit = 5): array {
    $db = get_db();
    $stmt = $db->prepare("
        SELECT e.*, i.iteration_num
        FROM emails e
        JOIN iterations i ON e.iteration_id = i.id
        WHERE e.industry = ?
        ORDER BY e.total_score DESC
        LIMIT ?
    ");
    $stmt->execute([$industry, $limit]);
    return $stmt->fetchAll();
}

function get_iteration_history(int $limit = 50): array {
    $db = get_db();
    $stmt = $db->prepare("
        SELECT * FROM iterations ORDER BY iteration_num DESC LIMIT ?
    ");
    $stmt->execute([$limit]);
    return $stmt->fetchAll();
}

function get_learnings_summary(int $limit = 30): array {
    $db = get_db();
    $stmt = $db->prepare("
        SELECT l.insight, l.created_at, i.iteration_num
        FROM learnings l
        JOIN iterations i ON l.iteration_id = i.id
        ORDER BY l.id DESC
        LIMIT ?
    ");
    $stmt->execute([$limit]);
    return $stmt->fetchAll();
}

function get_weight_history(): array {
    $db = get_db();
    return $db->query("
        SELECT w.*, i.iteration_num
        FROM weights w
        JOIN iterations i ON w.iteration_id = i.id
        ORDER BY i.iteration_num ASC
    ")->fetchAll();
}

function get_stats(): array {
    $db = get_db();

    $total_emails = $db->query("SELECT COUNT(*) as cnt FROM emails")->fetch()['cnt'];
    $total_iterations = $db->query("SELECT COUNT(*) as cnt FROM iterations")->fetch()['cnt'];
    $total_learnings = $db->query("SELECT COUNT(*) as cnt FROM learnings")->fetch()['cnt'];

    $best_ever = $db->query("SELECT MAX(total_score) as best FROM emails")->fetch()['best'];
    $avg_score = $db->query("SELECT AVG(total_score) as avg FROM emails")->fetch()['avg'];

    $latest = $db->query("SELECT * FROM iterations ORDER BY iteration_num DESC LIMIT 1")->fetch();

    $by_industry = $db->query("
        SELECT industry, AVG(total_score) as avg_score, MAX(total_score) as best_score, COUNT(*) as cnt
        FROM emails GROUP BY industry ORDER BY avg_score DESC
    ")->fetchAll();

    return [
        'total_emails' => (int)$total_emails,
        'total_iterations' => (int)$total_iterations,
        'total_learnings' => (int)$total_learnings,
        'best_score_ever' => round((float)($best_ever ?? 0), 2),
        'avg_score_overall' => round((float)($avg_score ?? 0), 2),
        'latest_iteration' => $latest,
        'by_industry' => $by_industry,
    ];
}
