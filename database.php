<?php
/**
 * Cold Email AI Optimizer - Database Layer
 *
 * MySQL operations for storing iterations, emails, learnings, and weights.
 */

require_once __DIR__ . '/config.php';

function get_db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $dsn = sprintf('mysql:host=%s;dbname=%s;charset=utf8mb4', DB_HOST, DB_NAME);
        $pdo = new PDO($dsn, DB_USER, DB_PASS, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    }
    return $pdo;
}

function create_tables(): void {
    $db = get_db();

    $db->exec("
        CREATE TABLE IF NOT EXISTS iterations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            iteration_num INT NOT NULL UNIQUE,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            industries JSON NOT NULL,
            avg_score DECIMAL(6,2) DEFAULT 0,
            best_score DECIMAL(6,2) DEFAULT 0,
            insights JSON,
            weight_snapshot JSON,
            INDEX idx_iter_num (iteration_num)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");

    $db->exec("
        CREATE TABLE IF NOT EXISTS emails (
            id INT AUTO_INCREMENT PRIMARY KEY,
            iteration_id INT NOT NULL,
            industry VARCHAR(50) NOT NULL,
            subject_line VARCHAR(500),
            body TEXT,
            hook_type VARCHAR(20),
            send_time VARCHAR(50),
            total_score DECIMAL(6,2) DEFAULT 0,
            subject_score DECIMAL(6,2) DEFAULT 0,
            hook_score DECIMAL(6,2) DEFAULT 0,
            personalization_score DECIMAL(6,2) DEFAULT 0,
            cta_score DECIMAL(6,2) DEFAULT 0,
            length_score DECIMAL(6,2) DEFAULT 0,
            timing_score DECIMAL(6,2) DEFAULT 0,
            spam_score DECIMAL(6,2) DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (iteration_id) REFERENCES iterations(id) ON DELETE CASCADE,
            INDEX idx_industry (industry),
            INDEX idx_total_score (total_score DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");

    $db->exec("
        CREATE TABLE IF NOT EXISTS learnings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            iteration_id INT NOT NULL,
            insight TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (iteration_id) REFERENCES iterations(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");

    $db->exec("
        CREATE TABLE IF NOT EXISTS weights (
            id INT AUTO_INCREMENT PRIMARY KEY,
            iteration_id INT NOT NULL,
            subject_line_quality DECIMAL(5,4) NOT NULL,
            hook_type_score DECIMAL(5,4) NOT NULL,
            personalization_depth DECIMAL(5,4) NOT NULL,
            cta_clarity DECIMAL(5,4) NOT NULL,
            email_length_score DECIMAL(5,4) NOT NULL,
            timing_score DECIMAL(5,4) NOT NULL,
            spam_avoidance DECIMAL(5,4) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (iteration_id) REFERENCES iterations(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
