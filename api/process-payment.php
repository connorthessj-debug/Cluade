<?php
/**
 * Le Besian Balls — Square Payment Processing
 *
 * This endpoint receives a payment token from the frontend Square SDK
 * and calls the Square Payments API to charge the card.
 *
 * SETUP:
 * 1. Install the Square PHP SDK via Composer:
 *    composer require square/square
 *
 * 2. Replace the credentials below with your Square API credentials.
 *
 * 3. For testing, use Sandbox credentials.
 *    For production, switch to Production credentials.
 */

header('Content-Type: application/json');

// ──────────────────────────────────────────────
// ▶ REPLACE THESE WITH YOUR SQUARE CREDENTIALS
// ──────────────────────────────────────────────
$SQUARE_ACCESS_TOKEN = 'YOUR_SQUARE_ACCESS_TOKEN'; // e.g. 'EAAAl...'
$SQUARE_LOCATION_ID  = 'YOUR_SQUARE_LOCATION_ID';  // e.g. 'LXXXX...'
$SQUARE_ENVIRONMENT  = 'sandbox'; // 'sandbox' or 'production'
// ──────────────────────────────────────────────

// Read request body
$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['sourceId']) || !isset($input['amount'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing required fields: sourceId, amount']);
    exit;
}

$sourceId = $input['sourceId'];
$amount   = (int)$input['amount']; // in cents
$currency = $input['currency'] ?? 'USD';
$customer = $input['customer'] ?? [];

// ──────────────────────────────────────────────
// Option A: Using Square PHP SDK (recommended)
// Uncomment this block after installing via Composer
// ──────────────────────────────────────────────
/*
require_once __DIR__ . '/../vendor/autoload.php';

use Square\SquareClient;
use Square\Models\CreatePaymentRequest;
use Square\Models\Money;

$client = new SquareClient([
    'accessToken' => $SQUARE_ACCESS_TOKEN,
    'environment' => $SQUARE_ENVIRONMENT,
]);

$money = new Money();
$money->setAmount($amount);
$money->setCurrency($currency);

$paymentRequest = new CreatePaymentRequest($sourceId, uniqid('lb_', true));
$paymentRequest->setAmountMoney($money);
$paymentRequest->setLocationId($SQUARE_LOCATION_ID);

if (!empty($customer['email'])) {
    $paymentRequest->setBuyerEmailAddress($customer['email']);
}

$paymentsApi = $client->getPaymentsApi();
$response = $paymentsApi->createPayment($paymentRequest);

if ($response->isSuccess()) {
    $payment = $response->getResult()->getPayment();
    echo json_encode([
        'success' => true,
        'paymentId' => $payment->getId(),
        'status' => $payment->getStatus(),
    ]);
} else {
    $errors = $response->getErrors();
    http_response_code(400);
    echo json_encode([
        'error' => $errors[0]->getDetail() ?? 'Payment failed',
    ]);
}
*/

// ──────────────────────────────────────────────
// Option B: Using cURL (no Composer needed)
// This works without installing any packages
// ──────────────────────────────────────────────

$baseUrl = $SQUARE_ENVIRONMENT === 'production'
    ? 'https://connect.squareup.com'
    : 'https://connect.squareupsandbox.com';

$payload = json_encode([
    'source_id'       => $sourceId,
    'idempotency_key' => uniqid('lb_', true),
    'amount_money'    => [
        'amount'   => $amount,
        'currency' => $currency,
    ],
    'location_id'     => $SQUARE_LOCATION_ID,
    'buyer_email_address' => $customer['email'] ?? null,
]);

$ch = curl_init("$baseUrl/v2/payments");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $payload,
    CURLOPT_HTTPHEADER     => [
        'Content-Type: application/json',
        "Authorization: Bearer $SQUARE_ACCESS_TOKEN",
        'Square-Version: 2024-01-18',
    ],
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$data = json_decode($response, true);

if ($httpCode === 200 && isset($data['payment'])) {
    echo json_encode([
        'success'   => true,
        'paymentId' => $data['payment']['id'],
        'status'    => $data['payment']['status'],
    ]);
} else {
    $errorMsg = $data['errors'][0]['detail'] ?? 'Payment failed';
    http_response_code(400);
    echo json_encode(['error' => $errorMsg]);
}
