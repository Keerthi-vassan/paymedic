"""Drives a real Razorpay Checkout session (netbanking, mock test bank) with
a headless browser to obtain a genuine success/fail outcome from Razorpay's
live test-mode system -- this module contains no local simulation logic.

Selectors are discovered against the live Checkout widget rather than
guessed from memory, since Razorpay's exact DOM isn't public API and can
shift between releases. DEBUG_SCREENSHOTS writes a numbered screenshot after
every step to /app/data/debug_screenshots/ when set, purely for developing
and diagnosing this driver -- never enabled in normal operation.
"""

import os
import time

from playwright.sync_api import Page, sync_playwright

DEBUG_SCREENSHOTS = os.environ.get("EXECUTION_DEBUG_SCREENSHOTS") == "1"
_SCREENSHOT_DIR = "/app/data/debug_screenshots"


class BrowserExecutionError(Exception):
    pass


def _snap(page: Page, label: str) -> None:
    if not DEBUG_SCREENSHOTS:
        return
    os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
    ts = int(time.time() * 1000)
    page.screenshot(path=f"{_SCREENSHOT_DIR}/{ts}_{label}.png")


def drive_netbanking_payment(
    harness_url: str,
    want_success: bool,
    timeout_seconds: int = 45,
) -> dict:
    """Opens the checkout harness, selects netbanking + a test bank, and
    clicks the mock bank's Success/Failure button matching want_success.

    This function's job ends at clicking that button -- it does NOT try to
    determine the payment outcome itself. Confirmed live (2026-08-24): the
    harness page's own `handler`/`payment.failed` JS callbacks (originally
    meant to signal the result via document.title) are unreliable under
    headless automation -- a payment was genuinely captured on Razorpay's
    side within 16s while the callback never fired, leaving the title stuck
    at RESULT_PENDING indefinitely. Polling Razorpay's own Orders API for
    the actual payment record (execution/__init__.py, after this returns)
    is both more reliable and more honestly "real" than trusting a
    client-side JS callback anyway.

    Returns {"clicked": bool, "detail": str}.
    """
    deadline_ms = timeout_seconds * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(harness_url, timeout=deadline_ms)
            _snap(page, "01_harness_loaded")

            frame = _wait_for_checkout_frame(page, deadline_ms)
            _snap(page, "02_checkout_frame")

            _dismiss_contact_details_modal(frame, deadline_ms)
            _snap(page, "02b_after_contact_modal")

            _select_netbanking(frame, deadline_ms)
            _snap(page, "03_netbanking_selected")

            _select_test_bank(frame, deadline_ms)
            _snap(page, "04_bank_selected")

            _click_mock_bank_outcome(page, frame, want_success, deadline_ms)
            _snap(page, "05_outcome_clicked")

            # Give the popup's form POST a moment to actually land on
            # Razorpay's server before the caller starts polling for it.
            page.wait_for_timeout(2000)
            return {"clicked": True, "detail": "outcome button clicked"}
        except Exception as exc:  # noqa: BLE001 -- any automation failure falls back to simulated
            try:
                _snap(page, "99_failure_state")
            except Exception:  # noqa: BLE001
                pass
            return {"clicked": False, "detail": str(exc)}
        finally:
            browser.close()


def _wait_for_checkout_frame(page: Page, timeout_ms: int):
    """Razorpay Checkout renders inside an iframe. Try Razorpay's documented
    frame name first; fall back to the first frame whose URL is on
    checkout.razorpay.com if that ever changes.
    """
    page.wait_for_timeout(1000)  # let the SDK inject the iframe
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "razorpay.com" in frame.url and frame != page.main_frame:
                return frame
        page.wait_for_timeout(300)
    raise BrowserExecutionError("Razorpay checkout iframe never appeared")


def _dismiss_contact_details_modal(frame, timeout_ms: int) -> None:
    """Razorpay's checkout asks for a mobile number in a blocking modal
    before showing payment methods, even with prefill.contact set -- the
    email prefill takes but the phone field still renders empty and
    required. Fill it and continue; if the modal never appears (e.g.
    Razorpay stops requiring this), this is a no-op within a short timeout.

    There are TWO "Continue" buttons in the DOM at this point (the card
    form's own, disabled, behind the modal, plus the modal's) -- a bare
    `button:has-text('Continue')).first` silently grabs whichever is first
    in DOM order, not necessarily the modal's. Scope the click to the
    button immediately following the mobile input instead of the frame at
    large, so it's always the modal's own Continue.
    """
    try:
        mobile_input = frame.locator("input[placeholder='Mobile number']").first
        if not mobile_input.is_visible(timeout=3000):
            return
        mobile_input.click(timeout=3000)
        # fill() sets .value + dispatches input/change directly; this
        # field's validation kept reporting "invalid" regardless of the
        # number tried, which pointed at the fill mechanism rather than the
        # number itself -- real keystroke-by-keystroke typing plus an
        # explicit blur matches what the live form actually expects.
        # Not a repeated-digit or sequential number -- Razorpay's checkout
        # rejects both (e.g. "9999999999", "9876543210") as "invalid" even
        # in test mode, confirmed live; a normal-looking scrambled number
        # passes validation.
        mobile_input.type("8296174035", delay=50)
        mobile_input.blur()
        frame.wait_for_timeout(300)
        # Nearest ancestor that itself contains a "Continue" button --
        # i.e. the modal's own container, whatever level that is -- then
        # click the Continue within just that scope.
        modal_scope = mobile_input.locator(
            "xpath=ancestor::*[.//button[contains(., 'Continue')]][1]"
        ).first
        modal_scope.locator("button:has-text('Continue')").first.click(timeout=5000)
        frame.wait_for_timeout(500)
    except Exception:  # noqa: BLE001 -- no modal present, or already past it
        return


def _select_netbanking(frame, timeout_ms: int) -> None:
    # [data-testid="Netbanking"] confirmed against the live Checkout widget
    # (2026-08-24); the rest are fallbacks in case Razorpay changes markup.
    candidates = [
        "[data-testid='Netbanking']",
        "text=Netbanking",
        "text=NetBanking",
        "[data-method='netbanking']",
        "button:has-text('Netbanking')",
    ]
    _click_first_match(frame, candidates, timeout_ms)


def _select_test_bank(frame, timeout_ms: int) -> None:
    """There is no literal "Test Bank" entry -- Razorpay's netbanking list
    in test mode shows the same real "Suggested Banks" as live mode, and
    any of them routes to a mock bank page since we're in test mode.
    Confirmed live (2026-08-24): Bank of Baroda's suggested-bank entry
    displays its own "currently facing issues" warning, so it's skipped in
    favor of Canara Bank, which loaded cleanly; the other suggested banks
    are kept as fallbacks in case availability shifts.
    """
    frame.wait_for_timeout(2500)  # bank list renders skeleton placeholders first
    _snap(frame.page, "03b_bank_list_loaded")
    candidates = [
        "text=Punjab National Bank",
        "text=IDBI",
        "text=PNB",
        "text=Canara Bank",
    ]
    _click_first_match(frame, candidates, timeout_ms)
    # Netbanking usually needs an explicit "Pay"/"Continue" submit after
    # picking a bank.
    submit_candidates = [
        "button:has-text('Pay')",
        "button[type='submit']",
        "text=Continue",
    ]
    try:
        _click_first_match(frame, submit_candidates, min(timeout_ms, 5000))
    except BrowserExecutionError:
        pass  # some flows auto-submit on bank selection -- not fatal


def _click_mock_bank_outcome(page: Page, frame, want_success: bool, timeout_ms: int) -> None:
    """The mock bank page (https://api.razorpay.com/v1/gateway/mocksharp/
    payment, titled "Razorpay Bank") opens as a genuine new browser popup,
    confirmed live (2026-08-24) -- not a redirect within `page` and not a
    frame within the checkout iframe, which is why earlier attempts here
    never found it. Its markup is exactly
    `<button data-val="S" class="success">Success</button>` /
    `data-val="F" class="danger">Failure</button>`.
    """
    context = page.context
    popup = _wait_for_new_page(context, page, timeout_ms)
    popup.wait_for_load_state("load", timeout=timeout_ms)

    label = "Success" if want_success else "Failure"
    candidates = [f"button:has-text('{label}')", f"[data-val='{'S' if want_success else 'F'}']"]
    _click_first_match(popup, candidates, timeout_ms)


def _wait_for_new_page(context, known_page: Page, timeout_ms: int) -> Page:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        others = [pg for pg in context.pages if pg != known_page]
        if others:
            return others[0]
        known_page.wait_for_timeout(300)
    raise BrowserExecutionError("mock bank popup never opened")


def _click_first_match(scope, selectors: list[str], timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    last_error = None
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                locator = scope.locator(selector).first
                if locator.is_visible(timeout=500):
                    # Razorpay's method-list has an entrance animation with a
                    # transient overlay-backdrop that intercepts early clicks
                    # -- Playwright's own actionability retry (not our outer
                    # loop) needs real headroom here, not the previous 2s.
                    locator.click(timeout=6000)
                    return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        scope.wait_for_timeout(300) if hasattr(scope, "wait_for_timeout") else time.sleep(0.3)
    raise BrowserExecutionError(f"none of {selectors} became clickable ({last_error})")


