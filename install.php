<?php
/**
 * Cold Email AI Optimizer - One-Time Installer
 *
 * Run this once after uploading files to Hostinger to set up the database.
 * Access via: https://yourdomain.com/install.php?secret=YOUR_CRON_SECRET
 *
 * IMPORTANT: Delete this file after installation for security.
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/database.php';

// Security check
$secret = $_GET['secret'] ?? ($argv[1] ?? '');
if ($secret !== CRON_SECRET) {
    http_response_code(403);
    die('Forbidden. Use: install.php?secret=YOUR_CRON_SECRET');
}

echo "<pre>\n";
echo "=== Cold Email AI Optimizer - Installer ===\n\n";

// Test database connection
try {
    echo "1. Testing database connection... ";
    $db = get_db();
    echo "OK\n";
} catch (Exception $e) {
    echo "FAILED\n";
    echo "   Error: " . $e->getMessage() . "\n";
    echo "   Check your .env file for correct DB_HOST, DB_NAME, DB_USER, DB_PASS\n";
    die("</pre>");
}

// Create tables
try {
    echo "2. Creating database tables... ";
    create_tables();
    echo "OK\n";
} catch (Exception $e) {
    echo "FAILED\n";
    echo "   Error: " . $e->getMessage() . "\n";
    die("</pre>");
}

// Verify tables
try {
    echo "3. Verifying tables...\n";
    $tables = ['iterations', 'emails', 'learnings', 'weights'];
    foreach ($tables as $table) {
        $stmt = $db->query("SHOW TABLES LIKE '$table'");
        $exists = $stmt->fetch() ? 'OK' : 'MISSING';
        echo "   - $table: $exists\n";
    }
} catch (Exception $e) {
    echo "   Verification error: " . $e->getMessage() . "\n";
}

// Test Claude API
echo "4. Testing Claude API connection... ";
if (empty(ANTHROPIC_API_KEY) || ANTHROPIC_API_KEY === 'sk-ant-xxxxx') {
    echo "SKIPPED (no API key configured)\n";
    echo "   Set ANTHROPIC_API_KEY in your .env file\n";
} else {
    require_once __DIR__ . '/claude_api.php';
    $test = claude_request(
        'You are a test. Respond with exactly: OK',
        'Say OK'
    );
    if ($test && stripos($test, 'OK') !== false) {
        echo "OK\n";
    } else {
        echo "FAILED (response: " . substr($test ?? 'null', 0, 100) . ")\n";
    }
}

// Check file permissions
echo "5. Checking file permissions...\n";
$log_file = __DIR__ . '/optimizer.log';
$writable = @file_put_contents($log_file, "Install test " . date('Y-m-d H:i:s') . "\n", FILE_APPEND);
echo "   - Log file writable: " . ($writable !== false ? 'OK' : 'FAILED') . "\n";

echo "\n=== Installation Complete ===\n\n";
echo "Next steps:\n";
echo "1. Set up a cron job in Hostinger hPanel:\n";
echo "   Command: /usr/bin/php " . __DIR__ . "/optimizer.php cron_secret=" . CRON_SECRET . "\n";
echo "   Interval: Every 10 minutes (*/10 * * * *)\n\n";
echo "2. Visit your dashboard: https://yourdomain.com/\n\n";
echo "3. DELETE THIS FILE (install.php) for security!\n";
echo "</pre>";
