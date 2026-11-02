import json
from pathlib import Path
import tempfile
import unittest

from tax_harness.chat import ChatSession
from tax_harness.chat import Ollama, explicit_month
from unittest.mock import patch
from urllib.error import URLError
from tax_harness.service import Service
from tax_harness.store import BusinessError, ROOT, initialize


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


class FakeModel:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.inputs = []

    def chat(self, messages, tools):
        self.inputs.append(messages)
        return next(self.responses)


ANSWER = {"role": "assistant", "content": "请查看工具返回的业务结果。"}


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-chat-", dir=ROOT / "data")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.db = self.directory / "chat.sqlite3"
        initialize(self.db)

    def session(self, model=None, user="U001"):
        return ChatSession(user, "C001", self.db, model or FakeModel(ANSWER), trace_dir=self.directory)

    def test_tool_loop_and_trace(self):
        session = self.session(FakeModel(call("totals", month="2026-09"), ANSWER))
        session.turn("查九月金额")
        rows = [json.loads(line) for line in session.trace_path.read_text(encoding="utf-8").splitlines()]
        result = next(r for r in rows if r["event"] == "tool_result")
        self.assertEqual("9622.06", result["result"]["data"]["invoice_total"])
        self.assertTrue(any(r["event"] == "model_input" for r in rows))
        self.assertEqual("2026-09", session.month)

    def test_proposal_never_saves_without_confirmation(self):
        session = self.session(FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "客户资料打印"}), ANSWER))
        reply = session.turn("给F002填用途客户资料打印")
        self.assertIn("尚未保存", reply)
        self.assertEqual("", session.service.invoice("U001", "C001", "F002")["purpose"])
        session.turn("/confirm")
        self.assertEqual("客户资料打印", Service(self.db).invoice("U001", "C001", "F002")["purpose"])
        self.assertEqual("", Service(self.db).invoice("U001", "C002", "F002")["purpose"])
        self.assertIn("没有待确认", session.turn("/confirm"))

    def test_correction_replaces_draft(self):
        session = self.session(FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "旧内容"}), ANSWER,
            call("prepare_update", invoice_id="F002", changes={"purpose": "更正内容"}), ANSWER))
        session.turn("填旧内容")
        session.turn("更正成更正内容")
        session.turn("/confirm")
        self.assertEqual("更正内容", session.service.invoice("U001", "C001", "F002")["purpose"])

    def test_question_clears_old_draft(self):
        session = self.session(FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "草稿"}), ANSWER, ANSWER, ANSWER))
        session.turn("用途填写草稿")
        session.turn("暂时不改，另问问题")
        self.assertIn("没有待确认", session.turn("/confirm"))

    def test_identity_and_immutable_fields_are_enforced(self):
        session = self.session()
        for name, args in (("invoice", {"invoice_id": "F002", "user": "U001"}), ("totals", {"month": "2026-09", "company": "C002"}),
            ("prepare_update", {"invoice_id": "F002", "changes": {"amount": "1"}}), ("update", {})):
            with self.assertRaises(BusinessError):
                session.dispatch(name, args)

    def test_read_only_user_cannot_propose(self):
        session = self.session(user="U002")
        with self.assertRaises(BusinessError):
            session.dispatch("prepare_update", {"invoice_id": "F002", "changes": {"purpose": "禁止"}})
        self.assertIsNone(session.pending)

    def test_no_default_month_and_new_session_has_no_history(self):
        session = self.session()
        self.assertIsNone(session.month)
        with self.assertRaises(BusinessError):
            session.dispatch("totals", {})
        session.turn("你好")
        other = self.session()
        self.assertEqual([], other.turns)
        self.assertNotEqual(session.session_id, other.session_id)

    def test_stale_draft_rejected(self):
        session = self.session()
        session.dispatch("prepare_update", {"invoice_id": "F002", "changes": {"purpose": "旧请求"}})
        Service(self.db).update("U001", "C001", "F002", {"remark": "其他会话更正"})
        with self.assertRaises(BusinessError) as exc:
            session.turn("/confirm")
        self.assertEqual("stale_draft", exc.exception.code)
        self.assertEqual("", session.service.invoice("U001", "C001", "F002")["purpose"])

    def test_invalid_tool_result_is_returned_to_model(self):
        model = FakeModel(call("invoice", invoice_id="F999"), ANSWER)
        session = self.session(model)
        session.turn("查F999")
        payload = json.loads(model.inputs[-1][-1]["content"])
        self.assertFalse(payload["ok"])
        self.assertEqual("not_found", payload["error"]["code"])

    def test_loop_is_bounded(self):
        session = self.session(FakeModel(*[call("invoice", invoice_id="F002") for _ in range(5)]))
        with self.assertRaises(BusinessError) as exc:
            session.turn("查询")
        self.assertEqual("tool_limit", exc.exception.code)

    def test_cancel(self):
        session = self.session()
        session.dispatch("prepare_update", {"invoice_id": "F002", "changes": {"purpose": "取消"}})
        session.turn("/cancel")
        self.assertIsNone(session.pending)

    def test_model_cannot_invent_content(self):
        model = FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "模型编造"}), ANSWER)
        session = self.session(model)
        session.turn("给F002补一下用途")
        self.assertIsNone(session.pending)
        payload = json.loads(model.inputs[-1][-1]["content"])
        self.assertEqual("content_not_explicit", payload["error"]["code"])

    def test_invalid_model_response_fails_closed(self):
        session = self.session(FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "草稿"}), {"role": "assistant", "content": None}))
        with self.assertRaises(BusinessError):
            session.turn("用途填草稿")
        self.assertIsNone(session.pending)
        self.assertEqual("", session.service.invoice("U001", "C001", "F002")["purpose"])

    def test_malformed_call_rejected(self):
        session = self.session(FakeModel({"role": "assistant", "tool_calls": ["not a function"]}))
        with self.assertRaises(BusinessError):
            session.turn("查询")

    def test_ollama_unavailable_is_explicit(self):
        with patch("tax_harness.chat.urlopen", side_effect=URLError("service offline")):
            with self.assertRaises(BusinessError) as exc:
                Ollama().chat([], [])
        self.assertEqual("model_unavailable", exc.exception.code)

    def test_guessed_month_cannot_query(self):
        model = FakeModel(call("totals", month="2026-09"), ANSWER)
        session = self.session(model)
        session.turn("查发票金额")
        result = json.loads(model.inputs[-1][-1]["content"])
        self.assertEqual("month_not_explicit", result["error"]["code"])
        self.assertIsNone(session.month)

    def test_month_source_validation_boundaries(self):
        self.assertTrue(explicit_month("2026-09", "2026年09月"))
        self.assertTrue(explicit_month("2026-09", "九月"))
        self.assertFalse(explicit_month("2026-01", "十一月"))
        self.assertFalse(explicit_month("2026-01", "11月"))
        self.assertFalse(explicit_month("2026-09", "2025年9月"))

    def test_correction_without_tool_is_reconsidered(self):
        session = self.session(FakeModel(call("prepare_update", invoice_id="F002", changes={"purpose": "原用途"}), ANSWER,
            {"role": "assistant", "content": "已更新"}, call("prepare_update", invoice_id="F002", changes={"purpose": "新用途"}), ANSWER))
        session.turn("用途原用途")
        session.turn("改成新用途")
        self.assertEqual("新用途", session.pending["changes"]["purpose"])


if __name__ == "__main__":
    unittest.main()
