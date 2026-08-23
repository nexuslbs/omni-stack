#!/usr/bin/env node
/* code_exec_runner_js — dsh-style codeRuntime seam (node) inside the toolbox.
 *
 * Reads the model-written program from stdin, wraps it as an async function
 * with top-level `return`/`await` support, and prints the completion value as
 * TYPED JSON on a marker line:
 *   __CODE_EXEC_OK__<json>   on success (value is real JSON, not a string)
 *   __CODE_EXEC_ERR__<json>  on failure (error as a FIELD, never a crash)
 *
 * Usage: code_exec_runner_js <args-json> [timeout-secs]
 * Installed at /usr/bin/code_exec_runner_js (requires nodejs, see
 * services/toolbox/Dockerfile). The timeout is a HARD in-container kill:
 * setTimeout(process.exit) fires mid-loop even if the docker exec client is
 * gone. */
const fs = require("fs");

const OK_MARKER = "__CODE_EXEC_OK__";
const ERR_MARKER = "__CODE_EXEC_ERR__";

function die(payload) {
  console.log(ERR_MARKER + JSON.stringify(payload));
  process.exit(0);
}

function main() {
  const argsJson = process.argv[2] ?? "null";
  const timeoutSecs = parseInt(process.argv[3] ?? "0", 10) || 0;
  let args;
  try {
    args = argsJson === "null" ? null : JSON.parse(argsJson);
  } catch (e) {
    return die({ error: "invalid args json: " + e });
  }
  let program;
  try {
    program = fs.readFileSync(0, "utf8");
  } catch (e) {
    return die({ error: "cannot read program from stdin: " + e });
  }
  if (!program.trim()) return die({ error: "empty program" });
  if (timeoutSecs > 0) {
    setTimeout(() => process.exit(124), timeoutSecs * 1000);
  }
  const body = program
    .split("\n")
    .map((l) => (l.trim() ? "  " + l : ""))
    .join("\n");
  const wrapper = `(async (args) => {\n${body}\n})`;
  let fn;
  try {
    // Running the model's program is the point of this runner.
    fn = eval(wrapper); // eslint-disable-line no-eval
  } catch (e) {
    return die({ error: "syntax error: " + e });
  }
  Promise.resolve()
    .then(() => fn(args))
    .then((result) => {
      console.log(
        OK_MARKER +
          JSON.stringify(result, (_k, v) => (v === undefined ? null : v))
      );
    })
    .catch((e) => {
      const stack = e && e.stack ? e.stack : String(e);
      return die({
        error: String((e && e.message) || e),
        traceback: stack,
      });
    });
}

main();
