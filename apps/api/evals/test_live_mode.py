"""Live action mode fails closed: no key / no charge id => no money moves.

Verifies the safety posture of ACTIONS_MODE=live without touching real Stripe.
"""
import pytest

from apps.api.actions.stripe_refund import StripeRefundAction
from apps.api.config import get_settings


@pytest.fixture()
def live_no_key(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ACTIONS_MODE", "live")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    yield
    get_settings.cache_clear()


def test_sandbox_still_default():
    get_settings.cache_clear()
    assert get_settings().actions_mode == "sandbox"
    res = StripeRefundAction().execute({"order_id": "55", "amount": 200}, {}, "k1")
    assert res["mode"] == "sandbox" and res["refund_id"].startswith("re_sandbox_")


def test_live_without_key_fails_closed(live_no_key):
    with pytest.raises(RuntimeError, match="STRIPE_API_KEY"):
        StripeRefundAction().execute({"order_id": "55", "amount": 200}, {"provider_charge_id": "ch_x"}, "k2")


def test_live_without_charge_id_fails_closed(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ACTIONS_MODE", "live")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    try:
        with pytest.raises(RuntimeError, match="provider_charge_id"):
            StripeRefundAction().execute({"order_id": "55", "amount": 200}, {}, "k3")
    finally:
        get_settings.cache_clear()
