<?php
declare(strict_types=1);

namespace Tests;

use PHPUnit\Framework\TestCase;
use Tests\Support\Http;
use Tests\Support\PhpServer;

final class AdminApiTest extends TestCase
{
    private string $baseUrl;
    private string $dataFile;
    private string $backupOriginal;

    protected function setUp(): void
    {
        $this->baseUrl = PhpServer::instance()->baseUrl();
        $this->dataFile = dirname(__DIR__, 2) . '/data/content.json';
        // Snapshot the existing content file so test mutations don't persist.
        $this->backupOriginal = (string) file_get_contents($this->dataFile);
    }

    protected function tearDown(): void
    {
        file_put_contents($this->dataFile, $this->backupOriginal);
        $backupDir = dirname(__DIR__, 2) . '/data/backups';
        if (is_dir($backupDir)) {
            foreach (glob($backupDir . '/content_*.json') ?: [] as $f) {
                @unlink($f);
            }
        }
    }

    public function test_load_returns_content_json(): void
    {
        $res = Http::request('GET', $this->baseUrl . '/api/admin-api.php?action=load');
        $this->assertSame(200, $res['status']);
        $this->assertSame('application/json', $res['headers']['content-type'] ?? '');
        $payload = json_decode($res['body'], true);
        $this->assertIsArray($payload);
        $this->assertArrayHasKey('site', $payload);
    }

    public function test_unknown_action_returns_400(): void
    {
        $res = Http::request('GET', $this->baseUrl . '/api/admin-api.php?action=bogus');
        $this->assertSame(400, $res['status']);
        $body = json_decode($res['body'], true);
        $this->assertArrayHasKey('error', $body);
    }

    public function test_missing_action_returns_400(): void
    {
        $res = Http::request('GET', $this->baseUrl . '/api/admin-api.php');
        $this->assertSame(400, $res['status']);
    }

    public function test_save_rejects_invalid_json(): void
    {
        $res = Http::request(
            'POST',
            $this->baseUrl . '/api/admin-api.php?action=save',
            '{not-json',
            ['Content-Type' => 'application/json']
        );
        $this->assertSame(400, $res['status']);
        $body = json_decode($res['body'], true);
        $this->assertSame('Invalid JSON', $body['error']);
    }

    public function test_save_persists_and_creates_backup(): void
    {
        $new = json_decode($this->backupOriginal, true);
        $new['site']['tagline'] = 'UNIT TEST TAGLINE';

        $res = Http::request(
            'POST',
            $this->baseUrl . '/api/admin-api.php?action=save',
            json_encode($new),
            ['Content-Type' => 'application/json']
        );
        $this->assertSame(200, $res['status']);
        $this->assertSame(['success' => true], json_decode($res['body'], true));

        $written = json_decode((string) file_get_contents($this->dataFile), true);
        $this->assertSame('UNIT TEST TAGLINE', $written['site']['tagline']);

        $backupDir = dirname(__DIR__, 2) . '/data/backups';
        $this->assertDirectoryExists($backupDir);
        $this->assertNotEmpty(glob($backupDir . '/content_*.json'));
    }

    public function test_options_request_short_circuits(): void
    {
        $res = Http::request('OPTIONS', $this->baseUrl . '/api/admin-api.php');
        $this->assertSame(200, $res['status']);
    }

    public function test_cors_headers_present(): void
    {
        $res = Http::request('GET', $this->baseUrl . '/api/admin-api.php?action=load');
        $this->assertSame('*', $res['headers']['access-control-allow-origin'] ?? null);
    }

    public function test_unauthenticated_save_currently_allowed_regression_marker(): void
    {
        // INTENTIONAL: the API has a TODO to add auth (admin-api.php:23-32).
        // This test documents the current behaviour so we notice when auth lands.
        $res = Http::request(
            'POST',
            $this->baseUrl . '/api/admin-api.php?action=save',
            $this->backupOriginal,
            ['Content-Type' => 'application/json']
        );
        $this->assertSame(200, $res['status'], 'Save is currently reachable without auth. Update this test when auth is added.');
    }
}
