<?php
/**
 * Cold Email AI Optimizer - JSON API Endpoints
 *
 * Serves data to the dashboard frontend via AJAX.
 * URL: /api.php?action=stats
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$action = $_GET['action'] ?? 'stats';

try {
    switch ($action) {
        case 'stats':
            echo json_encode(get_stats());
            break;

        case 'iterations':
            $limit = min(100, max(1, (int)($_GET['limit'] ?? 50)));
            echo json_encode(get_iteration_history($limit));
            break;

        case 'top_emails':
            $limit = min(50, max(1, (int)($_GET['limit'] ?? 20)));
            $industry = $_GET['industry'] ?? null;
            if ($industry && preg_match('/^[a-z_]+$/', $industry)) {
                echo json_encode(get_top_emails_for_industry($industry, $limit));
            } else {
                echo json_encode(get_top_emails($limit));
            }
            break;

        case 'learnings':
            $limit = min(100, max(1, (int)($_GET['limit'] ?? 30)));
            echo json_encode(get_learnings_summary($limit));
            break;

        case 'weights':
            echo json_encode(get_weight_history());
            break;

        case 'email_detail':
            $id = (int)($_GET['id'] ?? 0);
            if ($id > 0) {
                $db = get_db();
                $stmt = $db->prepare("SELECT e.*, i.iteration_num FROM emails e JOIN iterations i ON e.iteration_id = i.id WHERE e.id = ?");
                $stmt->execute([$id]);
                $email = $stmt->fetch();
                echo json_encode($email ?: ['error' => 'Not found']);
            } else {
                echo json_encode(['error' => 'Invalid ID']);
            }
            break;

        case 'industry_benchmarks':
            echo json_encode(INDUSTRY_BENCHMARKS);
            break;

        default:
            echo json_encode(['error' => 'Unknown action', 'available' => [
                'stats', 'iterations', 'top_emails', 'learnings', 'weights', 'email_detail', 'industry_benchmarks'
            ]]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
