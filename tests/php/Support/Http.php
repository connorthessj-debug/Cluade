<?php
declare(strict_types=1);

namespace Tests\Support;

final class Http
{
    /**
     * @param array<string,string> $headers
     * @return array{status:int, body:string, headers:array<string,string>}
     */
    public static function request(string $method, string $url, ?string $body = null, array $headers = []): array
    {
        $ch = curl_init($url);
        $hdrLines = [];
        foreach ($headers as $k => $v) {
            $hdrLines[] = "{$k}: {$v}";
        }
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HEADER => true,
            CURLOPT_HTTPHEADER => $hdrLines,
            CURLOPT_POSTFIELDS => $body,
            CURLOPT_TIMEOUT => 5,
        ]);
        $raw = curl_exec($ch);
        if ($raw === false) {
            $err = curl_error($ch);
            curl_close($ch);
            throw new \RuntimeException("curl failed: $err");
        }
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $hdrSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $rawHeaders = substr($raw, 0, $hdrSize);
        $body = substr($raw, $hdrSize);
        curl_close($ch);

        $parsed = [];
        foreach (preg_split('/\r?\n/', $rawHeaders) as $line) {
            if (str_contains($line, ':')) {
                [$k, $v] = explode(':', $line, 2);
                $parsed[strtolower(trim($k))] = trim($v);
            }
        }
        return ['status' => (int)$status, 'body' => $body, 'headers' => $parsed];
    }
}
