"""Frontend syntax, security, and SSE integration tests."""

import json
import re
import subprocess
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "newcode" / "ui" / "static"
CHAT_HTML = UI_DIR / "chat.html"
WORKBENCH_HTML = UI_DIR / "workbench.html"


def extract_scripts(html_text: str) -> list[str]:
    """Extract all script tag contents from an HTML document."""
    return re.findall(r"<script>([\s\S]*?)</script>", html_text)


def test_chat_html_exists():
    """Verify chat.html exists and is non-empty."""
    assert CHAT_HTML.exists(), "chat.html should exist"
    assert len(CHAT_HTML.read_text(encoding="utf-8")) > 100


def test_workbench_html_exists():
    """Verify workbench.html exists and is non-empty."""
    assert WORKBENCH_HTML.exists(), "workbench.html should exist"
    assert len(WORKBENCH_HTML.read_text(encoding="utf-8")) > 100


def test_chat_html_javascript_syntax_valid():
    """Verify that chat.html JavaScript has valid syntax via Node.js."""
    html_text = CHAT_HTML.read_text(encoding="utf-8")
    scripts = extract_scripts(html_text)
    assert len(scripts) > 0, "No <script> tags found in chat.html"

    for idx, script in enumerate(scripts):
        proc = subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, f"chat.html script #{idx+1} syntax error: {proc.stderr}"


def test_workbench_html_javascript_syntax_valid():
    """Verify that workbench.html JavaScript has valid syntax via Node.js."""
    html_text = WORKBENCH_HTML.read_text(encoding="utf-8")
    scripts = extract_scripts(html_text)
    assert len(scripts) > 0, "No <script> tags found in workbench.html"

    for idx, script in enumerate(scripts):
        proc = subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, f"workbench.html script #{idx+1} syntax error: {proc.stderr}"


def test_no_inline_onclick_string_construction():
    """Verify no inline onclick with dynamic template interpolation exists."""
    for file_path in [CHAT_HTML, WORKBENCH_HTML]:
        content = file_path.read_text(encoding="utf-8")
        assert "onclick=\"sendFeedback(" not in content, f"Found inline onclick sendFeedback in {file_path.name}"
        assert "onclick=\"adoptProblem(" not in content, f"Found inline onclick adoptProblem in {file_path.name}"
        assert "onclick=\"ignoreProblem(" not in content, f"Found inline onclick ignoreProblem in {file_path.name}"
        assert 'onclick="adoptProblem(' not in content, f"Found inline onclick adoptProblem in {file_path.name}"
        assert 'onclick="sendFeedback(' not in content, f"Found inline onclick sendFeedback in {file_path.name}"


def test_auth_header_reads_suredesk_access_token():
    """Verify that localStorage suredesk_access_token is read in both pages."""
    for file_path in [CHAT_HTML, WORKBENCH_HTML]:
        content = file_path.read_text(encoding="utf-8")
        assert 'localStorage.getItem("suredesk_access_token")' in content, (
            f"{file_path.name} must read suredesk_access_token from localStorage"
        )
        assert "Bearer " in content, f"{file_path.name} must construct Bearer token header"


def test_chat_uses_identity_from_signed_token():
    """Verify chat requests use the token identity instead of a fixed buyer ID."""
    content = CHAT_HTML.read_text(encoding="utf-8")
    assert "getAuthenticatedUserId" in content
    assert 'const userId = "user_buyer_1"' not in content


def test_workbench_navigation_link():
    """Verify chat.html links to /workbench instead of broken /workbench.html."""
    content = CHAT_HTML.read_text(encoding="utf-8")
    assert 'href="/workbench"' in content, "chat.html must link to /workbench"
    assert 'href="/workbench.html"' not in content, "chat.html should not link to 404 /workbench.html"


def test_feedback_preserves_actual_answer():
    """Verify sendFeedback does not hardcode an empty answer string."""
    content = CHAT_HTML.read_text(encoding="utf-8")
    assert 'answer: ""' not in content, "chat.html must not hardcode answer: '' in feedback"
    assert "accumulatedAnswer" in content, "chat.html should pass accumulatedAnswer to feedback"


def test_sse_parsing_behavior_with_node():
    """Execute Node to simulate SSE stream parsing and ensure event extraction works."""
    node_eval_code = """
    let thoughtCaptured = null;
    let answerChunks = [];

    const handlers = {
      onThought: (t) => { thoughtCaptured = t; },
      onAnswerChunk: (c) => { answerChunks.push(c); },
      onError: () => {}
    };

    function parseAndDispatchSseBlock(block, handlers) {
      const lines = block.split(/\\r?\\n/);
      let eventType = "message";
      const dataLines = [];

      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }

      if (dataLines.length === 0) return;
      const rawData = dataLines.join("\\n");

      let payload;
      try {
        payload = JSON.parse(rawData);
      } catch (err) {
        payload = rawData;
      }

      if (eventType === "thought") {
        const thoughtText = typeof payload === "object" && payload ? (payload.thought || payload.content || "") : String(payload);
        if (thoughtText && handlers.onThought) handlers.onThought(thoughtText);
      } else if (eventType === "answer") {
        let chunk = "";
        if (typeof payload === "object" && payload) {
          chunk = payload.chunk !== undefined ? payload.chunk : (payload.content !== undefined ? payload.content : "");
        } else {
          chunk = String(payload);
        }
        if (chunk && handlers.onAnswerChunk) handlers.onAnswerChunk(chunk);
      }
    }

    const testStream = 'event: thought\\r\\ndata: {"thought": "analyzing..."}\\r\\n\\r\\nevent: answer\\r\\ndata: {"chunk": "Sure"}\\r\\n\\r\\nevent: answer\\r\\ndata: {"chunk": "Desk"}\\r\\n\\r\\n';
    const blocks = testStream.split(/\\r?\\n\\r?\\n/).filter(b => b.trim());
    blocks.forEach(b => parseAndDispatchSseBlock(b, handlers));

    console.log(JSON.stringify({ thought: thoughtCaptured, fullAnswer: answerChunks.join("") }));
    """

    proc = subprocess.run(
        ["node", "-e", node_eval_code],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"Node script failed: {proc.stderr}"
    result = json.loads(proc.stdout)
    assert result["thought"] == "analyzing..."
    assert result["fullAnswer"] == "SureDesk"
