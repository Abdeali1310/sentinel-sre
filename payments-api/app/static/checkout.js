const button = document.getElementById("pay");
const statusLine = document.getElementById("status");
const receipt = document.getElementById("receipt");
const receiptOrder = document.getElementById("receipt-order");
const errorBanner = document.getElementById("error");

const AMOUNT = Number(button.dataset.amount);
const CURRENCY = button.dataset.currency;

function setPending(pending) {
  button.disabled = pending;
  button.dataset.pending = String(pending);
  button.querySelector(".label").textContent = pending ? "Processing" : "Pay now";
  if (pending) {
    statusLine.textContent = "Contacting your bank\u2026";
  }
}

function showReceipt(orderId) {
  receiptOrder.textContent = orderId;
  receipt.hidden = false;
  errorBanner.hidden = true;
}

function showFailure() {
  errorBanner.hidden = false;
  receipt.hidden = true;
}

function newIdempotencyKey() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return "key-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

button.addEventListener("click", async () => {
  setPending(true);
  statusLine.textContent = "";
  receipt.hidden = true;
  errorBanner.hidden = true;

  try {
    const response = await fetch("/payments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": newIdempotencyKey(),
      },
      body: JSON.stringify({ amount: AMOUNT, currency: CURRENCY }),
    });

    if (response.ok) {
      const payment = await response.json();
      showReceipt(payment.order_id);
      statusLine.textContent = "";
    } else {
      showFailure();
      statusLine.textContent = "";
    }
  } catch (networkError) {
    showFailure();
    statusLine.textContent = "";
  } finally {
    setPending(false);
  }
});
