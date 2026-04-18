<?php
declare(strict_types=1);

namespace Tests\Support;

/**
 * Spins up PHP's built-in server against the repo root so tests can exercise
 * the real api/*.php endpoints over HTTP. One server instance per suite.
 */
final class PhpServer
{
    private static ?self $instance = null;

    /** @var resource|null */
    private $process = null;
    private string $host = '127.0.0.1';
    private int $port;
    private string $docroot;

    public static function instance(): self
    {
        if (self::$instance === null) {
            self::$instance = new self();
            self::$instance->start();
            register_shutdown_function(fn () => self::$instance?->stop());
        }
        return self::$instance;
    }

    private function __construct()
    {
        $this->docroot = dirname(__DIR__, 3);
        $this->port = 18000 + random_int(0, 999);
    }

    public function baseUrl(): string
    {
        return "http://{$this->host}:{$this->port}";
    }

    private function start(): void
    {
        $descriptors = [
            0 => ['pipe', 'r'],
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ];
        $cmd = sprintf(
            '%s -S %s:%d -t %s',
            escapeshellarg(PHP_BINARY),
            escapeshellarg($this->host),
            $this->port,
            escapeshellarg($this->docroot)
        );
        $this->process = proc_open($cmd, $descriptors, $pipes);
        if (!is_resource($this->process)) {
            throw new \RuntimeException('Failed to start PHP built-in server');
        }
        // Wait briefly for the server to accept connections
        $deadline = microtime(true) + 3.0;
        while (microtime(true) < $deadline) {
            $fp = @fsockopen($this->host, $this->port, $errno, $errstr, 0.1);
            if ($fp) {
                fclose($fp);
                return;
            }
            usleep(50_000);
        }
        throw new \RuntimeException('PHP built-in server did not start');
    }

    private function stop(): void
    {
        if (is_resource($this->process)) {
            proc_terminate($this->process);
            proc_close($this->process);
            $this->process = null;
        }
    }
}
