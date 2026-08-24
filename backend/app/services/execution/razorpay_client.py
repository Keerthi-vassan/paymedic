"""Thin wrapper around Razorpay's real REST API (test mode). Every call here
hits Razorpay's actual servers -- there is no local simulation in this module,
unlike the rest of the pipeline. Auth is HTTP Basic with the test-mode
key_id/key_secret, per Razorpay's documented API auth scheme.
"""

import httpx

from app.config import settings


class RazorpayAPIError(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.razorpay_base_url,
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        timeout=15.0,
    )


def create_order(amount: int, currency: str = "INR", receipt: str | None = None) -> dict:
    """amount is in paise, matching Razorpay's native unit -- no conversion
    needed anywhere in this integration.
    """
    payload = {"amount": amount, "currency": currency, "payment_capture": 1}
    if receipt:
        payload["receipt"] = receipt

    with _client() as client:
        response = client.post("/orders", json=payload)
    if response.status_code >= 400:
        raise RazorpayAPIError(f"create_order failed: {response.status_code} {response.text}")
    return response.json()


def fetch_order_payments(order_id: str) -> list[dict]:
    with _client() as client:
        response = client.get(f"/orders/{order_id}/payments")
    if response.status_code >= 400:
        raise RazorpayAPIError(f"fetch_order_payments failed: {response.status_code} {response.text}")
    return response.json().get("items", [])


def fetch_payment(payment_id: str) -> dict:
    with _client() as client:
        response = client.get(f"/payments/{payment_id}")
    if response.status_code >= 400:
        raise RazorpayAPIError(f"fetch_payment failed: {response.status_code} {response.text}")
    return response.json()
