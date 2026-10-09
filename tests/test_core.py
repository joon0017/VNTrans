import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from vntrans_core import Preset, Store, protect_key, translate


class CoreTests(unittest.TestCase):
    def test_eztrans_language_pair_and_provider_validation(self):
        Preset(provider="eztrans", source="ja", target="ko").validate()
        for values in (dict(provider="unknown"), dict(provider="eztrans", target="en"),
                       dict(provider="eztrans", source="en"), dict(eztrans_path=1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Preset(**values).validate()

    def test_old_presets_default_to_azure_and_new_provider_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            (store.directory / "presets.json").write_text('[{"name": "Old game"}]', encoding="utf-8")
            self.assertEqual(store.load_presets()[0].provider, "azure")
            preset = Preset(provider="eztrans", eztrans_path="C:/example/ezTrans XP")
            store.save([preset], "")
            self.assertEqual(store.load_presets(), [preset])

    def test_negative_monitor_coordinates_and_bounds(self):
        desktop = dict(left=-1920, top=-200, width=3840, height=1280)
        Preset(x=-1800, y=-100).validate(desktop)
        with self.assertRaises(ValueError):
            Preset(x=-2000).validate(desktop)
        with self.assertRaises(ValueError):
            Preset(x=1800).validate(desktop)

    def test_invalid_inputs(self):
        for values in (dict(interval=0), dict(w=-1), dict(source="ja&to=en"),
                       dict(name=" "), dict(x=True), dict(region="eastasia\r\n")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Preset(**values).validate()

    def test_dpapi_unicode_and_empty_key_roundtrip(self):
        for key in ("", "test-secret-일본어-日本語"):
            encoded = key.encode("utf-8")
            encrypted = protect_key(encoded)
            self.assertNotEqual(encoded, encrypted)
            self.assertEqual(protect_key(encrypted, decrypt=True), encoded)

    def test_presets_and_key_persist_without_plaintext_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            presets = [Preset(name="ゲーム", x=-100), Preset(name="Other", source="en", target="ja")]
            store.save(presets, "test-secret")
            self.assertEqual(store.load_presets(), presets)
            self.assertEqual(store.load_key(), "test-secret")
            self.assertNotIn("test-secret", (store.directory / "presets.json").read_text(encoding="utf-8"))
            self.assertEqual({p.name for p in store.directory.iterdir()}, {"presets.json", "key.dat"})

    def test_corrupted_presets_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            (store.directory / "presets.json").write_text("not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load_presets()

    def test_translation_utf8_request_and_response(self):
        result = [{"translations": [{"text": "안녕하세요"}]}]
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(result).encode())) as request:
            self.assertEqual(translate("こんにちは", Preset(region="eastasia"), "fake-key"), "안녕하세요")
        req = request.call_args.args[0]
        self.assertEqual(json.loads(req.data), [{"Text": "こんにちは"}])
        self.assertIn("from=ja&to=ko", req.full_url)
        self.assertEqual(req.get_header("Ocp-apim-subscription-region"), "eastasia")

    def test_rate_limit_error_explains_recovery(self):
        error = urllib.error.HTTPError("https://example.test", 429, "Limited", {}, None)
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaisesRegex(RuntimeError, "Increase the interval"):
            translate("hello", Preset(), "fake-key")


if __name__ == "__main__":
    unittest.main()
