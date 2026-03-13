<?php
/**
 * Cold Email AI Optimizer - Setup Script
 *
 * Run once to initialize the SQLite database.
 * Usage: php install.php
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';

echo "=== Cold Email AI Optimizer - Setup ===\n\n";

// Check for .env
if (!file_exists(__DIR__ . '/.env')) {
    if (file_exists(__DIR__ . '/.env.example')) {
        copy(__DIR__ . '/.env.example', __DIR__ . '/.env');
        echo "1. Created .env from .env.example\n";
        echo "   >>> EDIT .env NOW and add your ANTHROPIC_API_KEY <<<\n\n";
    } else {
        echo "1. WARNING: No .env.example found. Create .env manually.\n\n";
    }
} else {
    echo "1. .env file exists - OK\n";
}

// Create data directory
$data_dir = dirname(DB_PATH);
if (!is_dir($data_dir)) {
    mkdir($data_dir, 0755, true);
    echo "2. Created data directory: $data_dir\n";
} else {
    echo "2. Data directory exists - OK\n";
}

// Create database tables
try {
    create_tables();
    echo "3. Database tables created - OK (" . DB_PATH . ")\n";
} catch (Exception $e) {
    echo "3. Database ERROR: " . $e->getMessage() . "\n";
    exit(1);
}

// Verify tables
try {
    $db = get_db();
    $tables = ['iterations', 'emails', 'learnings', 'weights'];
    echo "4. Verifying tables:\n";
    foreach ($tables as $table) {
        $stmt = $db->query("SELECT name FROM sqlite_master WHERE type='table' AND name='$table'");
        $exists = $stmt->fetch() ? 'OK' : 'MISSING';
        echo "   - $table: $exists\n";
    }
} catch (Exception $e) {
    echo "4. Verification error: " . $e->getMessage() . "\n";
}

// Test Claude API
echo "5. Testing Claude API: ";
if (empty(ANTHROPIC_API_KEY) || ANTHROPIC_API_KEY === 'sk-ant-xxxxx') {
    echo "SKIPPED (set ANTHROPIC_API_KEY in .env first)\n";
} else {
    require_once __DIR__ . '/claude_api.php';
    $test = claude_request('Respond with exactly one word: OK', 'Test');
    if ($test && stripos($test, 'OK') !== false) {
        echo "OK - Claude API is working\n";
    } else {
        echo "FAILED (response: " . substr($test ?? 'null', 0, 100) . ")\n";
        echo "   Check your ANTHROPIC_API_KEY in .env\n";
    }
}

// Check PHP version and extensions
echo "6. Environment:\n";
echo "   - PHP " . PHP_VERSION . "\n";
echo "   - SQLite: " . (extension_loaded('pdo_sqlite') ? 'OK' : 'MISSING - install php-sqlite3') . "\n";
echo "   - cURL: " . (extension_loaded('curl') ? 'OK' : 'MISSING - install php-curl') . "\n";
echo "   - JSON: " . (extension_loaded('json') ? 'OK' : 'MISSING') . "\n";

echo "\n=== Setup Complete ===\n\n";
echo "To run:\n";
echo "  php start.php              # Start optimizer loop + dashboard\n";
echo "  php start.php --once       # Run one iteration only\n";
echo "  php start.php --dashboard  # Dashboard only (no optimizer)\n";
echo "\n";
echo "Dashboard will be at: http://localhost:" . DASHBOARD_PORT . "\n";
