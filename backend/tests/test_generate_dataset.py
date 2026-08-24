from app.config import settings
from scripts.generate_dataset import generate_failed_payments


def test_real_candidates_absent_when_execution_disabled():
    """Default state (razorpay_execution_enabled=False): output must be
    byte-identical in shape to the fully-simulated system -- no is_real rows,
    same count -- so a judge's clean clone with no Razorpay keys behaves
    exactly as it always has.
    """
    assert settings.razorpay_execution_enabled is False
    rows = generate_failed_payments(count=100, seed=42)

    assert len(rows) == 100
    assert all("is_real" not in row for row in rows)


def test_real_candidates_injected_when_execution_enabled(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_execution_enabled", True)
    monkeypatch.setattr(settings, "razorpay_real_txn_count", 4)

    rows = generate_failed_payments(count=100, seed=42)
    real_rows = [row for row in rows if row.get("is_real")]

    assert len(rows) == 100
    assert len(real_rows) == 4

    non_cluster_instruments = {
        row["payment_instrument_id"]
        for row in rows
        if not row.get("is_real") and row["true_root_cause"] == "possible_fraud"
    }
    for row in real_rows:
        assert row["payment_method"] == "netbanking"
        assert row["true_root_cause"] in {"gateway_timeout", "network_drop", "auth_failure"}
        assert row["error_reason"] is not None
        assert row["payment_instrument_id"] not in non_cluster_instruments


def test_real_candidate_count_configurable(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_execution_enabled", True)
    monkeypatch.setattr(settings, "razorpay_real_txn_count", 2)

    rows = generate_failed_payments(count=100, seed=42)
    real_rows = [row for row in rows if row.get("is_real")]

    assert len(real_rows) == 2
