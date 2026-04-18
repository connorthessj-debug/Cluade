<?php
declare(strict_types=1);

namespace Tests;

use PHPUnit\Framework\TestCase;
use Tests\Support\Http;
use Tests\Support\PhpServer;

/**
 * Only exercises input-validation paths of process-payment.php.
 * Square API calls are not exercised because the cURL target is hardcoded
 * in the script and credentials are placeholders. A future refactor should
 * make the Square base URL and access token injectable so happy-path can
 * be tested against a fake Square server.
 */
final class ProcessPaymentTest extends TestCase
{
    private string $url;

    protected function setUp(): void
    {
        $this->url = PhpServer::instance()->baseUrl() . '/api/process-payment.php';
    }

    public function test_missing_body_returns_400(): void
    {
        $res = Http::request('POST', $this->url, '', ['Content-Type' => 'application/json']);
        $this->assertSame(400, $res['status']);
        $body = json_decode($res['body'], true);
        $this->assertStringContainsString('sourceId', $body['error']);
    }

    public function test_missing_amount_returns_400(): void
    {
        $res = Http::request(
            'POST',
            $this->url,
            json_encode(['sourceId' => 'cnon:card-nonce-ok']),
            ['Content-Type' => 'application/json']
        );
        $this->assertSame(400, $res['status']);
    }

    public function test_missing_sourceid_returns_400(): void
    {
        $res = Http::request(
            'POST',
            $this->url,
            json_encode(['amount' => 1000]),
            ['Content-Type' => 'application/json']
        );
        $this->assertSame(400, $res['status']);
    }

    public function test_invalid_json_returns_400(): void
    {
        $res = Http::request('POST', $this->url, '{bad', ['Content-Type' => 'application/json']);
        $this->assertSame(400, $res['status']);
    }
}
