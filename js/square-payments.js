/* ===== Square Web Payments SDK Integration =====
 *
 * HOW TO SET UP:
 * 1. Go to https://developer.squareup.com and create an application
 * 2. Get your Application ID and Location ID
 * 3. Replace the placeholder values below
 * 4. For testing, use Sandbox credentials. For production, use Production credentials.
 * 5. In index.html, change the Square SDK script URL:
 *      Sandbox:    https://sandbox.web.squarecdn.com/v1/square.js
 *      Production: https://web.squarecdn.com/v1/square.js
 */

// ──────────────────────────────────────────────
// ▶ REPLACE THESE WITH YOUR SQUARE CREDENTIALS
// ──────────────────────────────────────────────
const SQUARE_APP_ID     = 'YOUR_SQUARE_APPLICATION_ID';   // e.g. 'sandbox-sq0idb-XXXX' or 'sq0idp-XXXX'
const SQUARE_LOCATION_ID = 'YOUR_SQUARE_LOCATION_ID';     // e.g. 'LXXXXXXXXXXXXXXXX'

// Set to 'sandbox' for testing, 'production' for live payments
const SQUARE_ENVIRONMENT = 'sandbox';

// ──────────────────────────────────────────────

let squarePayments = null;
let squareCard = null;

/**
 * Initialize the Square payment form.
 * Called automatically when user opens checkout modal.
 */
async function initSquarePayment() {
    const container = document.getElementById('card-container');
    if (!container) return;

    // Don't re-init if already attached
    if (squareCard) {
        return;
    }

    // Check if Square SDK loaded
    if (typeof window.Square === 'undefined') {
        container.innerHTML = '<p style="color:#ef4444;text-align:center;padding:16px;">Square payment SDK failed to load. Check your internet connection.</p>';
        return;
    }

    // Check if credentials are set
    if (SQUARE_APP_ID === 'YOUR_SQUARE_APPLICATION_ID') {
        container.innerHTML = `
            <div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:16px;text-align:center;font-size:0.9rem;">
                <strong>Payment Setup Required</strong><br>
                Open <code>js/square-payments.js</code> and add your Square Application ID and Location ID.
            </div>
        `;
        return;
    }

    try {
        squarePayments = window.Square.payments(SQUARE_APP_ID, SQUARE_LOCATION_ID);
        squareCard = await squarePayments.card();
        await squareCard.attach('#card-container');
    } catch (err) {
        console.error('Square init error:', err);
        container.innerHTML = '<p style="color:#ef4444;text-align:center;">Failed to load payment form. Please try again.</p>';
    }
}

/**
 * Handle the payment when user clicks "Pay".
 * This tokenizes the card, then sends the token to your backend.
 */
async function handlePayment() {
    const statusEl = document.getElementById('payment-status');
    const payBtn = document.getElementById('pay-button');
    statusEl.textContent = '';
    statusEl.className = 'payment-status';

    // Validate form
    const name = document.getElementById('checkout-name').value.trim();
    const email = document.getElementById('checkout-email').value.trim();
    const phone = document.getElementById('checkout-phone').value.trim();

    if (!name || !email || !phone) {
        statusEl.textContent = 'Please fill in all contact fields.';
        statusEl.className = 'payment-status error';
        return;
    }

    if (!squareCard) {
        statusEl.textContent = 'Payment form not loaded. Please refresh and try again.';
        statusEl.className = 'payment-status error';
        return;
    }

    payBtn.disabled = true;
    payBtn.textContent = 'Processing...';

    try {
        // Tokenize the card
        const result = await squareCard.tokenize();

        if (result.status === 'OK') {
            const token = result.token;

            // ───────────────────────────────────────────
            // ▶ SEND TOKEN TO YOUR BACKEND API
            // Replace this URL with your actual payment endpoint.
            // Your backend should call Square's Payments API
            // to charge the card using this token.
            // ───────────────────────────────────────────
            const response = await fetch('/api/process-payment.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sourceId: token,
                    amount: Math.round(getCheckoutTotal() * 100), // amount in cents
                    currency: 'USD',
                    customer: { name, email, phone },
                    fulfillment: selectedFulfillment,
                    items: cart.map(c => {
                        const item = findItem(c.id);
                        return { name: item.name, qty: c.qty, price: item.price };
                    })
                })
            });

            const data = await response.json();

            if (data.success) {
                statusEl.textContent = 'Payment successful! Your order has been placed.';
                statusEl.className = 'payment-status success';
                cart = [];
                saveCart();
                setTimeout(() => {
                    closeCheckout();
                    statusEl.textContent = '';
                }, 3000);
            } else {
                throw new Error(data.error || 'Payment failed');
            }
        } else {
            throw new Error(result.errors?.[0]?.message || 'Card tokenization failed');
        }
    } catch (err) {
        console.error('Payment error:', err);
        statusEl.textContent = `Payment failed: ${err.message}`;
        statusEl.className = 'payment-status error';
    } finally {
        payBtn.disabled = false;
        payBtn.textContent = `Pay ${document.getElementById('pay-total').textContent}`;
    }
}

/**
 * Calculate total including delivery fee.
 */
function getCheckoutTotal() {
    const subtotal = getCartTotal();
    if (selectedFulfillment === 'delivery' && siteContent) {
        const { fulfillment } = siteContent;
        if (subtotal < fulfillment.free_delivery_minimum) {
            return subtotal + fulfillment.delivery_fee;
        }
    }
    return subtotal;
}
