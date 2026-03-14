<?php
/**
 * Le Besian Balls — Admin API
 *
 * Simple PHP backend to load/save the content.json file.
 * This powers the admin dashboard's ability to persist changes.
 *
 * SECURITY: In production, add authentication before this API.
 * See the AUTH section below for where to add password protection.
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// ──────────────────────────────────────────────
// ▶ AUTH: Add your authentication check here.
// Example with a simple password (use proper auth in production):
//
// session_start();
// if (!isset($_SESSION['admin_logged_in'])) {
//     http_response_code(401);
//     echo json_encode(['error' => 'Unauthorized']);
//     exit;
// }
// ──────────────────────────────────────────────

$dataFile = __DIR__ . '/../data/content.json';
$action = $_GET['action'] ?? '';

switch ($action) {
    case 'load':
        if (!file_exists($dataFile)) {
            http_response_code(404);
            echo json_encode(['error' => 'Content file not found']);
            exit;
        }
        $json = file_get_contents($dataFile);
        echo $json;
        break;

    case 'save':
        $input = file_get_contents('php://input');
        $data = json_decode($input, true);

        if ($data === null) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid JSON']);
            exit;
        }

        // Create a backup before overwriting
        if (file_exists($dataFile)) {
            $backupDir = __DIR__ . '/../data/backups';
            if (!is_dir($backupDir)) {
                mkdir($backupDir, 0755, true);
            }
            copy($dataFile, $backupDir . '/content_' . date('Y-m-d_H-i-s') . '.json');
        }

        // Write the new content
        $result = file_put_contents(
            $dataFile,
            json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );

        if ($result === false) {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to write file. Check file permissions.']);
            exit;
        }

        echo json_encode(['success' => true]);
        break;

    default:
        http_response_code(400);
        echo json_encode(['error' => 'Invalid action. Use ?action=load or ?action=save']);
        break;
}
