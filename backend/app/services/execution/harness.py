"""A minimal page whose only job is to auto-open Razorpay's real Checkout
widget for a given order, so the headless browser in browser_driver.py has
something to drive. Razorpay Checkout is a JS SDK meant to be embedded in a
merchant's own page (not a standalone hosted URL), so this route exists
purely as that embedding surface for automation -- it is not a documented
API endpoint and is never linked from the dashboard.

Outcome signaling: rather than scraping Razorpay's DOM for a result, this
page writes the outcome into `document.title` (RESULT_SUCCESS:<payment_id> /
RESULT_FAILED:<payment_id_or_empty> / RESULT_DISMISSED), which
browser_driver.py polls for -- simpler and more stable than depending on
exact DOM structure for the final state.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/internal", tags=["internal"])

_HARNESS_HTML = """<!DOCTYPE html>
<html>
<head><title>RESULT_PENDING</title></head>
<body>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
  const params = new URLSearchParams(window.location.search);
  const options = {
    key: params.get("key_id"),
    order_id: params.get("order_id"),
    amount: params.get("amount"),
    currency: "INR",
    name: "Paymedic",
    description: "Recovery attempt (test mode)",
    prefill: {
      name: "Paymedic Test",
      email: "test@paymedic.invalid",
      contact: "+919999999999"
    },
    handler: function (response) {
      document.title = "RESULT_SUCCESS:" + response.razorpay_payment_id;
    },
    modal: {
      ondismiss: function () {
        document.title = "RESULT_DISMISSED";
      }
    }
  };
  const rzp = new Razorpay(options);
  rzp.on("payment.failed", function (response) {
    const pid = (response.error && response.error.metadata && response.error.metadata.payment_id) || "";
    document.title = "RESULT_FAILED:" + pid;
  });
  rzp.open();
</script>
</body>
</html>
"""


@router.get("/checkout-harness", response_class=HTMLResponse)
def checkout_harness():
    return _HARNESS_HTML
