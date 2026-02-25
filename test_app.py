import importlib
import os
import unittest

from fastapi import HTTPException


def load_app_module(dspace_api_value: str):
    os.environ["DSPACE_API"] = dspace_api_value
    module = importlib.import_module("app")
    return importlib.reload(module)


class AppBehaviorTests(unittest.TestCase):
    def setUp(self):
        self._old_dspace_api = os.environ.get("DSPACE_API")

    def tearDown(self):
        if self._old_dspace_api is None:
            os.environ.pop("DSPACE_API", None)
        else:
            os.environ["DSPACE_API"] = self._old_dspace_api

    def test_mock_catalog_returns_expected_navigation(self):
        app_module = load_app_module("MOCK")

        feed = app_module.root_navigation(page=0, size=20)

        self.assertEqual(feed["metadata"]["numberOfItems"], 2)
        self.assertEqual(len(feed["navigation"]), 2)
        self.assertEqual(feed["navigation"][0]["title"], "Audiobook Library")

    def test_mock_community_unknown_uuid_returns_404(self):
        app_module = load_app_module("MOCK")

        with self.assertRaises(HTTPException) as ctx:
            app_module.get_community("does-not-exist")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_search_without_query_returns_empty_publications(self):
        app_module = load_app_module("MOCK")

        result = app_module.search_publications(query=None)

        self.assertEqual(result["metadata"]["title"], "No search terms")
        self.assertEqual(result["publications"], [])

    def test_fetch_dspace_json_maps_upstream_error_to_502(self):
        app_module = load_app_module("https://example.org/server/api")

        class FakeClient:
            def get_json(self, path, params=None, absolute_url=False, timeout_seconds=None):
                raise app_module.UpstreamServiceError("upstream unavailable")

        app_module.IS_MOCK = False
        app_module.DS_CLIENT = FakeClient()

        with self.assertRaises(HTTPException) as ctx:
            app_module.fetch_dspace_json("/core/communities/search/top")

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("upstream unavailable", str(ctx.exception.detail))

    def test_readiness_check_in_mock_mode_returns_ready(self):
        app_module = load_app_module("MOCK")

        result = app_module.readiness_check()

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["mockMode"])

    def test_readiness_check_maps_upstream_failure_to_503(self):
        app_module = load_app_module("https://example.org/server/api")

        class FakeClient:
            def get_json(self, path, params=None, absolute_url=False, timeout_seconds=None):
                raise app_module.UpstreamServiceError("timeout")

        app_module.IS_MOCK = False
        app_module.DS_CLIENT = FakeClient()

        with self.assertRaises(HTTPException) as ctx:
            app_module.readiness_check()

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Readiness check failed", str(ctx.exception.detail))

    def test_cached_lookup_only_calls_upstream_once_for_same_key(self):
        app_module = load_app_module("https://example.org/server/api")
        app_module.LOOKUP_CACHE.clear()

        class FakeClient:
            def __init__(self):
                self.calls = 0

            def get_json(self, path, params=None, absolute_url=False, timeout_seconds=None):
                self.calls += 1
                return {"page": {"totalElements": 1, "totalPages": 1, "number": 0}}

        fake = FakeClient()
        app_module.IS_MOCK = False
        app_module.DS_CLIENT = fake

        app_module.fetch_dspace_json_cached("/core/communities/search/top", params={"page": 0, "size": 1})
        app_module.fetch_dspace_json_cached("/core/communities/search/top", params={"page": 0, "size": 1})

        self.assertEqual(fake.calls, 1)

    def test_set_runtime_dspace_api_switches_to_mock_and_clears_cache(self):
        app_module = load_app_module("https://example.org/server/api")
        app_module.LOOKUP_CACHE.set("x", {"ok": True})

        app_module.set_runtime_dspace_api("MOCK")

        self.assertTrue(app_module.IS_MOCK)
        self.assertIsNone(app_module.DS_CLIENT)
        self.assertIsNone(app_module.LOOKUP_CACHE.get("x"))


if __name__ == "__main__":
    unittest.main()
