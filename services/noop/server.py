#!/usr/bin/env python3
"""Noop-provider: test-tool-caller model processes JSON scripts as tool calls.

When model is `test-tool-caller`, the FIRST user message must be a JSON array
defining tool calls. Each item: {name, tool, arguments} or [batch items].

Variable references: ${step_name.field} resolves from prior step outputs.

Each turn: count completed assistant tool_calls -> return next or summary.
"""
import json, os, uuid, time, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler


def _log(msg):
    """Simple stderr logging visible in docker logs."""
    print(f"[noop-debug] {msg}", flush=True)


def _resolve_args(arguments, outputs):
    """Resolve ${step.field} placeholders from previous step outputs."""
    if not arguments:
        return {}
    resolved = {}
    for key, value in arguments.items():
        if isinstance(value, str) and "${" in value:
            s = value
            for sn, so in outputs.items():
                if isinstance(so, dict):
                    for fname, fval in so.items():
                        p = "${" + sn + "." + fname + "}"
                        if p in s:
                            s = s.replace(p, str(fval))
            resolved[key] = s
        else:
            resolved[key] = value
    return resolved


def _build_tool_call(tool, args, call_id):
    return {"id": call_id, "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)},
            "index": 0}


def _parse_script(messages):
    """Parse script from the first user message. Returns None if not a script."""
    for msg in messages:
        if msg.get("role") == "user":
            raw = msg.get("content", "")
            if raw is None:
                break
            try:
                p = json.loads(raw)
                if isinstance(p, list):
                    _log(f"_parse_script: found {len(p)} top-level items")
                    return p
            except Exception:
                pass
            break
    return None


def _count_completed_and_outputs(messages, script):
    if not script:
        return 0, {}
    all_steps = []
    for item in script:
        if isinstance(item, list):
            for sub in item:
                all_steps.append(sub)
        elif isinstance(item, dict):
            all_steps.append(item)
    _log(f"_count: {len(all_steps)} steps in script")
    assistant_tc_ids = []
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                tid = tc.get("id", "")
                if tid:
                    assistant_tc_ids.append(tid)
    _log(f"_count: {len(assistant_tc_ids)} assistant tc_ids: {assistant_tc_ids}")
    tool_results = {}
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id:
                raw = msg.get("content", "")
                if isinstance(raw, dict):
                    tool_results[tc_id] = raw
                elif isinstance(raw, str):
                    try:
                        tool_results[tc_id] = json.loads(raw)
                    except Exception:
                        tool_results[tc_id] = {"text": raw}
    _log(f"_count: {len(tool_results)} tool results: {list(tool_results.keys())}")
    completed = sum(1 for tid in assistant_tc_ids if tid in tool_results)
    _log(f"_count: {completed}/{len(all_steps)} completed")
    outputs = {}
    for idx, step in enumerate(all_steps):
        if idx < len(assistant_tc_ids):
            tc_id = assistant_tc_ids[idx]
            step_name = step.get("name", "")
            if tc_id in tool_results and step_name:
                outputs[step_name] = tool_results[tc_id]
    return completed, outputs


def _generate(script, completed, outputs):
    if not script:
        return "No valid script found. Send a JSON array of tool calls.", None
    total_steps = 0
    for item in script:
        if isinstance(item, list):
            total_steps += len(item)
        else:
            total_steps += 1
    _log(f"_generate: {completed}/{total_steps} steps done")
    if completed >= total_steps:
        parts = []
        for item in script:
            if isinstance(item, list):
                bp = []
                for s in item:
                    sn = s.get("name", "?")
                    st = s.get("tool", "?")
                    out = outputs.get(sn, {})
                    mark = "✅" if out else "❌"
                    bp.append(f"    {mark} `{st}` -> {json.dumps(out)[:120]}")
                parts.append(f"  **Batch ({len(item)} tools):**\n" + "\n".join(bp))
            elif isinstance(item, dict):
                sn = item.get("name", "?")
                st = item.get("tool", "?")
                out = outputs.get(sn, {})
                mark = "✅" if out else "❌"
                parts.append(f"  {mark} `{st}` -> {json.dumps(out)[:200]}")
        summary = "\n".join(parts)
        return (
            f"This is a reply to your message from the **test provider** `noop` "
            f"using the model **test-tool-caller**.\n\n"
            f"All **{total_steps}** tool call batch(es) completed.\n\n"
            f"{summary}"
        ), None
    flat_idx = 0
    for idx, item in enumerate(script):
        if isinstance(item, list):
            for si, sub in enumerate(item):
                if flat_idx == completed:
                    name = sub.get("name", f"step_{idx}_{si}")
                    tool = sub.get("tool", "")
                    args = sub.get("arguments", {})
                    resolved = _resolve_args(args, outputs)
                    call_id = f"call_{name}_{uuid.uuid4().hex[:8]}"
                    _log(f"_generate: step {completed} -> {tool}({name})")
                    return None, [_build_tool_call(tool, resolved, call_id)]
                flat_idx += 1
        elif isinstance(item, dict):
            if flat_idx == completed:
                name = item.get("name", f"step_{idx}")
                tool = item.get("tool", "")
                args = item.get("arguments", {})
                resolved = _resolve_args(args, outputs)
                call_id = f"call_{name}_{uuid.uuid4().hex[:8]}"
                _log(f"_generate: step {completed} -> {tool}({name})")
                return None, [_build_tool_call(tool, resolved, call_id)]
            flat_idx += 1
    return "All steps processed.", None


class NoopHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json(200, {"object": "list", "data": [
                {"id": "test-model-1", "object": "model", "created": int(time.time()), "owned_by": "noop"},
                {"id": "test-model-2", "object": "model", "created": int(time.time()), "owned_by": "noop"},
                {"id": "test-tool-caller", "object": "model", "created": int(time.time()), "owned_by": "noop"},
            ]})
        elif self.path in ("/health", "/"):
            self._send_json(200, {"status": "ok", "provider": "noop"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle()
        else:
            self._send_json(404, {"error": "Not found"})

    def _handle(self):
        cl = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(cl) if cl else b"{}"
        try:
            body = json.loads(raw)
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return
        model = body.get("model", "test-model-1")
        msgs = body.get("messages", [])
        roles = [m.get("role") for m in msgs]
        _log(f"_handle(model={model}, msgs={len(msgs)}, roles={roles})")
        for m in msgs:
            c = m.get("content", "")
            if c and len(c) > 5:
                _log(f"_handle: {m['role']} content (first 400): {c[:400]}")
        if model == "test-tool-caller":
            try:
                content, tcs = self._handle_tool_caller(msgs)
            except Exception:
                _log(f"ERROR: {traceback.format_exc()}")
                content, tcs = f"Error: {traceback.format_exc()[:200]}", None
        else:
            content, tcs = self._handle_default(model, msgs)
        resp = {
            "id": f"noop-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant"},
                         "finish_reason": "stop" if tcs is None else "tool_calls"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
        msg = resp["choices"][0]["message"]
        msg["content"] = content
        if tcs is not None:
            msg["tool_calls"] = tcs
            resp["choices"][0]["finish_reason"] = "tool_calls"
        _log(f"_handle: finish={resp['choices'][0]['finish_reason']}, tcs={len(tcs) if tcs else 0}")
        self._send_json(200, resp)

    def _handle_tool_caller(self, msgs):
        script = _parse_script(msgs)
        if script is None:
            user_text = self._last_text(msgs)
            if user_text:
                _log("_handle_tool_caller: no script but user msg exists, echoing")
                return self._handle_default("test-tool-caller", user_text)
            _log("_handle_tool_caller: no script and no user msg, returning plan text")
            return self._plan_text(msgs), None
        completed, outputs = _count_completed_and_outputs(msgs, script)
        return _generate(script, completed, outputs)

    def _plan_text(self, msgs):
        """Return a plan-like text when agent sends only system messages (planning phase)."""
        roles = [m.get("role") for m in msgs]
        _log(f"_plan_text: roles={roles}")
        return "Proceed with the next step."

    def _handle_default(self, model, user_msg):
        if user_msg is None:
            user_msg = "(no user message)"
        quoted = "\n".join(f"> {l}" for l in user_msg.split("\n"))
        return (f"This is a reply to your message from the **test provider** `noop` "
                f"using the model **{model}**.\n\nYour original message:\n\n{quoted}", None)

    def _last_text(self, msgs):
        for m in reversed(msgs):
            if m.get("role") == "user":
                return m.get("content", "") or ""
        return ""

    def _send_json(self, status, data):
        b = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def main():
    port = int(os.environ.get("PORT", "9090"))
    _log(f"Starting on port {port}")
    HTTPServer(("0.0.0.0", port), NoopHandler).serve_forever()


if __name__ == "__main__":
    main()
