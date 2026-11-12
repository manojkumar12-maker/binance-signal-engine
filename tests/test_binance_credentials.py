import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src.config import settings
from src.secrets import SecretBox
from src.settings_manager import SettingsManager
from src.storage import Storage


def _manager(tmp_path):
    storage = Storage(path=str(tmp_path / "creds.db"))
    box = SecretBox(key="unit-test-passphrase", key_path=str(tmp_path / "unused.key"))
    return storage, SettingsManager(storage, secret_box=box), box


def _restore_settings():
    settings.binance_api_key = ""
    settings.binance_api_secret = ""
    settings.binance_testnet_api_key = ""
    settings.binance_testnet_api_secret = ""


def test_secret_box_roundtrip(tmp_path):
    box = SecretBox(key="unit-test-passphrase", key_path=str(tmp_path / "k"))
    token = box.encrypt("super-secret-value")
    assert token != "super-secret-value"
    assert box.decrypt(token) == "super-secret-value"
    assert box.encrypt("super-secret-value") != token


def test_save_credentials_masks_and_never_stores_plaintext(tmp_path):
    storage, sm, box = _manager(tmp_path)
    key, secret = "PUBLICKEY1234567890", "PRIVATESECRET0987654321"
    try:
        res = sm.save_binance_credentials(key, secret, "testnet")
        assert res["ok"] is True
        status = sm.get_binance_status()
        assert status["testnet"]["configured"] is True
        assert status["testnet"]["api_key_last4"].endswith(key[-4:])
        blob = json.dumps(status)
        assert key not in blob
        assert secret not in blob
        stored = storage.get_secret("binance_testnet_api_key")
        assert stored is not None
        assert key not in stored["ciphertext"]
        assert secret not in (storage.get_secret("binance_testnet_api_secret")["ciphertext"])
        assert box.decrypt(stored["ciphertext"]) == key
    finally:
        _restore_settings()


def test_load_into_settings_restores_credentials(tmp_path):
    storage, sm, _ = _manager(tmp_path)
    try:
        sm.save_binance_credentials("PUBLICKEY1234567890", "PRIVATESECRET0987654321", "live")
        _restore_settings()
        sm.load_into_settings()
        assert settings.binance_api_key == "PUBLICKEY1234567890"
        assert settings.binance_api_secret == "PRIVATESECRET0987654321"
    finally:
        _restore_settings()


def test_clear_credentials(tmp_path):
    storage, sm, _ = _manager(tmp_path)
    try:
        sm.save_binance_credentials("PUBLICKEY1234567890", "PRIVATESECRET0987654321", "testnet")
        res = sm.clear_binance_credentials("testnet")
        assert res["ok"] is True
        assert sm.get_binance_status()["testnet"]["configured"] is False
        assert storage.get_secret("binance_testnet_api_key") is None
        assert settings.binance_testnet_api_key == ""
    finally:
        _restore_settings()


def test_invalid_inputs_rejected(tmp_path):
    storage, sm, _ = _manager(tmp_path)
    assert sm.save_binance_credentials("k", "s", "testnet")["ok"] is False
    assert sm.save_binance_credentials("PUBLICKEY1234567890", "PRIVATESECRET0987654321", "demo")["ok"] is False
    assert sm.clear_binance_credentials("demo")["ok"] is False


def test_connection_check_does_not_leak_secret(tmp_path, monkeypatch):
    storage, sm, _ = _manager(tmp_path)
    key, secret = "PUBLICKEY1234567890", "PRIVATESECRET0987654321"
    try:
        sm.save_binance_credentials(key, secret, "testnet")

        class FakeClient:
            def __init__(self, api_key="", api_secret="", testnet=True):
                self.testnet = testnet

            def sync_time(self):
                pass

            def account(self):
                return {
                    "canTrade": True,
                    "canWithdraw": False,
                    "canDeposit": True,
                    "accountType": "MARGIN",
                    "totalWalletBalance": "100",
                    "availableBalance": "50",
                }

            def close(self):
                pass

        import src.binance_client as bc
        monkeypatch.setattr(bc, "BinanceClient", FakeClient)

        res = sm.test_binance_connection("testnet")
        assert res["ok"] is True
        assert res["can_trade"] is True
        assert res["network"] == "testnet"
        blob = json.dumps(res)
        assert key not in blob
        assert secret not in blob
    finally:
        _restore_settings()
