#!/usr/bin/env python3
"""code_exec_runner — dsh-style codeRuntime seam inside the toolbox container.

Runs a model-written program (read from stdin) with a JSON `args` object,
supports top-level `return` and `await`, and prints the completion value as
TYPED JSON on a marker line:

    __CODE_EXEC_OK__<json>      on success (value is real JSON, not a string)
    __CODE_EXEC_ERR__<json>     on failure (error is a FIELD, never a crash)

Usage: code_exec_runner <args-json> [timeout-secs]
The program is read from stdin. Installed at /usr/bin/code_exec_runner in the
omni-stack toolbox image (see services/toolbox/Dockerfile). The timeout is a
HARD in-container kill: a SIGALRM (default disposition) terminates the process
mid-loop even if the docker exec client is gone.
"""
import asyncio
import json
import os
import signal
import sys
import traceback

OK_MARKER = "__CODE_EXEC_OK__"
ERR_MARKER = "__CODE_EXEC_ERR__"


def _die(err_payload):
    """Emit the error as a FIELD on a resolved result, then exit cleanly."""
    print(ERR_MARKER + json.dumps(err_payload), flush=True)
    sys.exit(0)


def _wrap(program, async_):
    lines = program.splitlines()
    body = "\n".join(("    " + ln if ln.strip() else "") for ln in lines)
    head = (
        "async def __code_exec_main__(args):"
        if async_
        else "def __code_exec_main__(args):"
    )
    return head + "\n" + body + "\n"


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: code_exec_runner <args-json> [timeout-secs]\n")
        sys.exit(2)
    try:
        args = json.loads(sys.argv[1]) if sys.argv[1] != "null" else None
    except Exception as e:  # noqa: BLE001
        _die({"error": f"invalid args json: {e}"})
    try:
        timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    except ValueError:
        timeout = 0
    if timeout > 0:
        def _alarm(*_):
            # os.write is async-signal-safe-ish in CPython; emit the error as a
            # FIELD (marker line) so the caller sees "timed out", then exit
            # hard — mid-loop, without unwinding the program.
            os.write(
                1,
                (ERR_MARKER
                 + json.dumps({"error": f"program timed out after {timeout}s"})
                 + "\n").encode(),
            )
            os._exit(124)
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout)

    program = sys.stdin.read()
    if not program.strip():
        _die({"error": "empty program"})

    fn = None
    last_syntax = None
    for async_ in (False, True):
        try:
            compiled = compile(_wrap(program, async_), "<code_exec>", "exec")
        except SyntaxError as e:
            last_syntax = e
            continue
        ns = {"args": args}
        exec(compiled, ns)  # noqa: S102 - running the model's program is the point
        fn = ns["__code_exec_main__"]
        try:
            if async_:
                result = asyncio.run(fn(args))
            else:
                result = fn(args)
        except Exception as e:  # noqa: BLE001
            _die({"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
        break
    if fn is None:
        _die({"error": f"syntax error: {last_syntax}"})

    # Serialize the completion value as TYPED JSON (lossless boundary).
    try:
        payload = json.dumps(result, default=str)
    except Exception as e:  # noqa: BLE001
        _die({"error": f"return value is not JSON-serializable: {e}", "repr": repr(result)})
    print(OK_MARKER + payload, flush=True)


if __name__ == "__main__":
    main()
