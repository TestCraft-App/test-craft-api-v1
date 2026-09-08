import logging
import os
import unittest
from importlib import import_module
from unittest.mock import MagicMock, call, patch

from flask import g

os.environ["FLASK_ENV"] = "local"
os.environ.setdefault("OPENAI_API_KEY", "server-key")

api_module = import_module("app.api")
create_app = import_module("main").create_app


class FakeModelListResponse:
    def __init__(self, model_ids):
        self.model_ids = model_ids

    def model_dump(self):
        return {"data": [{"id": model_id} for model_id in self.model_ids]}


class FakeStreamChunk:
    def model_dump(self):
        return {
            "choices": [{"delta": {"content": "hello"}}],
            "ignored": "provider metadata",
        }


class ModelConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_models_endpoint_returns_only_gpt_5_6_catalog_with_luna_default(self):
        openai_client = MagicMock()
        openai_client.models.list.return_value = FakeModelListResponse([
            "gpt-4o",
            "gpt-5.6-luna",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
        ])

        with patch.object(api_module, "OpenAI", return_value=openai_client):
            response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["default_model"], "gpt-5.6-luna")
        self.assertFalse(response.json["model_selection_enabled"])
        self.assertEqual(
            [model["id"] for model in response.json["models"]],
            ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
        )
        self.assertEqual(
            [model["label"] for model in response.json["models"]],
            ["GPT-5.6 Sol", "GPT-5.6 Terra", "GPT-5.6 Luna"],
        )
        self.assertTrue(all(model["tokens"] == 128000 for model in api_module.SUPPORTED_MODELS))

    def test_unknown_tokenizer_falls_back_without_cloud_logger(self):
        fallback_encoding = MagicMock()
        fallback_encoding.encode.return_value = [1, 2, 3]
        local_logger = MagicMock(spec=logging.Logger)

        with (
            patch.object(
                api_module.tiktoken,
                "encoding_for_model",
                side_effect=[KeyError("unknown model"), fallback_encoding],
            ) as encoding_for_model,
            patch.object(api_module, "logger", local_logger),
        ):
            result = api_module.is_prompt_length_valid("prompt", "gpt-5.6-luna")

        self.assertTrue(result)
        self.assertEqual(
            encoding_for_model.call_args_list,
            [call("gpt-5.6-luna"), call("gpt-4o")],
        )
        local_logger.warning.assert_called_once_with(
            "Failed to get encoding for model gpt-5.6-luna, falling back to gpt-4o"
        )

    def test_missing_model_uses_server_key_and_luna_with_medium_reasoning(self):
        openai_client = MagicMock()
        completion = object()
        openai_client.chat.completions.create.return_value = completion

        with (
            patch.object(api_module, "OpenAI", return_value=openai_client) as openai,
            patch.object(api_module, "is_prompt_length_valid", return_value=True),
            patch.object(api_module.config, "API_KEY", "server-key"),
        ):
            result = api_module.call_openai_api("prompt", "developer", False)

        self.assertIs(result, completion)
        openai.assert_called_once_with(
            api_key="server-key",
            organization="org-vrjw201KSt5hgeiFuytTSaHb",
        )
        request = openai_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning_effort"], "medium")
        self.assertNotIn("temperature", request)

    def test_user_key_can_select_sol_or_terra(self):
        for model in ("gpt-5.6-sol", "gpt-5.6-terra"):
            with self.subTest(model=model):
                openai_client = MagicMock()
                openai_client.chat.completions.create.return_value = object()

                with (
                    patch.object(api_module, "OpenAI", return_value=openai_client) as openai,
                    patch.object(api_module, "is_prompt_length_valid", return_value=True),
                ):
                    api_module.call_openai_api(
                        "prompt",
                        "developer",
                        False,
                        model=model,
                        key="user-key",
                    )

                openai.assert_called_once_with(api_key="user-key")
                request = openai_client.chat.completions.create.call_args.kwargs
                self.assertEqual(request["model"], model)
                self.assertEqual(request["reasoning_effort"], "medium")
                self.assertNotIn("temperature", request)

    def test_explicit_older_model_keeps_existing_temperature_behavior(self):
        openai_client = MagicMock()
        openai_client.chat.completions.create.return_value = object()

        with (
            patch.object(api_module, "OpenAI", return_value=openai_client),
            patch.object(api_module, "is_prompt_length_valid", return_value=True),
        ):
            api_module.call_openai_api(
                "prompt",
                "developer",
                False,
                model="gpt-4o",
                key="user-key",
            )

        request = openai_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["temperature"], 0.5)
        self.assertNotIn("reasoning_effort", request)

    def test_legacy_stream_preserves_sse_shape(self):
        openai_client = MagicMock()
        openai_client.chat.completions.create.return_value = [FakeStreamChunk()]

        with (
            patch.object(api_module, "OpenAI", return_value=openai_client),
            patch.object(api_module, "is_prompt_length_valid", return_value=True),
        ):
            response = api_module.call_openai_api(
                "prompt",
                "developer",
                True,
                model="gpt-5.6-luna",
                key="user-key",
            )

        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(
            list(response.response),
            [b'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n'],
        )

    def test_v2_stream_forces_luna_and_preserves_sse_shape(self):
        openai_client = MagicMock()
        openai_client.chat.completions.create.return_value = [FakeStreamChunk()]

        with self.app.test_request_context(
            "/api/v2/stream",
            method="POST",
            json={
                "prompt": "prompt",
                "systemMessage": "system",
                "model": "gpt-5.6-sol",
            },
        ):
            g.user = {"googleId": "user-123"}
            with (
                patch.object(api_module, "OpenAI", return_value=openai_client),
                patch.object(api_module, "is_limit_reached", return_value=False),
                patch.object(api_module, "is_prompt_length_valid", return_value=True),
                patch.object(api_module, "increment_usage") as increment_usage,
            ):
                response = api_module.v2_stream.__wrapped__()

            increment_usage.assert_called_once_with("user-123")

        request = openai_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning_effort"], "medium")
        self.assertNotIn("temperature", request)
        self.assertEqual(request["user"], "free-tier:user-123")
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(
            list(response.response),
            [b'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n'],
        )


if __name__ == "__main__":
    unittest.main()
