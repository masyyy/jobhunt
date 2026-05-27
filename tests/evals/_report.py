"""HTML report renderer for eval results."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime

from tests.evals._runner import CaseResult, TimelineEvent


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _format_tool_result(result: object) -> str:
    """Render a tool return as readable text. Tries JSON first, falls back to str()."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(result)


def _render_timeline(timeline: list[TimelineEvent]) -> str:
    if not timeline:
        return '<div class="muted">No tool calls.</div>'
    items: list[str] = []
    for idx, event in enumerate(timeline, start=1):
        step_label = f'<span class="step-num">{idx}</span>'
        if event.kind == "tool_call":
            args_pretty = json.dumps(event.args or {}, indent=2, default=str, ensure_ascii=False)
            items.append(
                f'<li class="event tool-call">'
                f"{step_label}"
                f'<div class="event-body">'
                f'<div class="event-header"><span class="event-kind">tool call</span>'
                f'<span class="tool-name">{_esc(event.name or "")}</span></div>'
                f'<pre class="args">{_esc(args_pretty)}</pre>'
                f"</div></li>"
            )
        elif event.kind == "tool_return":
            result_text = _format_tool_result(event.result)
            items.append(
                f'<li class="event tool-return">'
                f"{step_label}"
                f'<div class="event-body">'
                f'<div class="event-header"><span class="event-kind">tool return</span>'
                f'<span class="tool-name">{_esc(event.name or "")}</span></div>'
                f'<pre class="result">{_esc(result_text)}</pre>'
                f"</div></li>"
            )
        elif event.kind == "text":
            items.append(
                f'<li class="event text">'
                f"{step_label}"
                f'<div class="event-body">'
                f'<div class="event-header"><span class="event-kind">assistant</span></div>'
                f'<div class="markdown-body" data-md="{_esc(json.dumps(event.text or ""))}"></div>'
                f"</div></li>"
            )
    return f'<ol class="timeline">{"".join(items)}</ol>'


def _render_case(result: CaseResult) -> str:
    case = result.case
    status = "pass" if result.passed else "fail"
    status_label = "PASS" if result.passed else "FAIL"

    judge_summary = ""
    if result.judge_score is not None:
        judge_summary = (
            f'<span class="judge-pill" title="Judge score (threshold {case.judge_threshold:.2f})">'
            f"judge {result.judge_score:.2f}</span>"
        )

    judge_block = ""
    if result.judge_score is not None:
        judge_block = (
            f'<div class="judge"><strong>Judge:</strong> '
            f'<span class="score">{result.judge_score:.2f}</span> '
            f"(threshold {case.judge_threshold:.2f})"
            f'<div class="muted">{_esc(result.judge_reasoning or "")}</div>'
            f"</div>"
        )

    failure_block = ""
    if result.failure_reason:
        failure_block = f'<div class="failure"><strong>Failure:</strong> {_esc(result.failure_reason)}</div>'

    # Failures default to expanded so regressions are visible without clicking.
    open_attr = " open" if not result.passed else ""

    return (
        f'<details class="case {status}"{open_attr}>'
        f'<summary class="case-summary">'
        f'<span class="status {status}">{status_label}</span>'
        f'<span class="case-id">{_esc(case.id)}</span>'
        f'<span class="toolbox">{_esc(case.toolbox.value)}</span>'
        f"{judge_summary}"
        f"</summary>"
        f'<div class="case-body">'
        f'<div class="prompt"><strong>Prompt:</strong><pre>{_esc(case.user_prompt)}</pre></div>'
        f'<div class="response"><strong>Response:</strong>'
        f'<div class="markdown-body" data-md="{_esc(json.dumps(result.response))}"></div>'
        f"</div>"
        f'<div class="tools-section"><strong>Agent chain:</strong>{_render_timeline(result.timeline)}</div>'
        f"{judge_block}"
        f"{failure_block}"
        f"</div>"
        f"</details>"
    )


_STYLE = """
body { font-family: -apple-system, system-ui, sans-serif; max-width: 1100px;
       margin: 2rem auto; padding: 0 1rem; color: #111; }
h1 { margin-bottom: 0.25rem; }
.summary { color: #555; margin-bottom: 1rem; }
.controls { margin-bottom: 1rem; display: flex; gap: 0.5rem; }
.controls button { font: inherit; font-size: 0.85rem; padding: 0.3rem 0.7rem;
                   border: 1px solid #ccc; background: #f5f5f5; border-radius: 4px;
                   cursor: pointer; }
.controls button:hover { background: #eaeaea; }
.case { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 0.5rem;
        background: #fff; }
.case.pass { border-left: 6px solid #2e7d32; }
.case.fail { border-left: 6px solid #c62828; }
.case.fail .case-summary { background: #fff5f5; }
.case-summary { display: flex; align-items: center; gap: 0.75rem;
                padding: 0.6rem 1rem; cursor: pointer; list-style: none;
                user-select: none; }
.case-summary::-webkit-details-marker { display: none; }
.case-summary::before { content: "▸"; color: #888; font-size: 0.8rem;
                        width: 0.8rem; transition: transform 0.15s; }
.case[open] > .case-summary::before { transform: rotate(90deg); }
.case[open] > .case-summary { border-bottom: 1px solid #eee; }
.case-body { padding: 0.75rem 1.25rem 1rem 1.25rem; }
.status { font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 4px;
          font-size: 0.75rem; letter-spacing: 0.05em; }
.status.pass { background: #e8f5e9; color: #2e7d32; }
.status.fail { background: #ffebee; color: #c62828; }
.case-id { font-family: ui-monospace, Menlo, monospace; font-weight: 600;
           font-size: 0.9rem; }
.toolbox { color: #666; font-size: 0.8rem; }
.judge-pill { margin-left: auto; font-family: ui-monospace, Menlo, monospace;
              font-size: 0.75rem; color: #6a1b9a; background: #f3e5f5;
              padding: 0.1rem 0.45rem; border-radius: 3px; }
pre { background: #f5f5f5; padding: 0.75rem; border-radius: 4px;
      white-space: pre-wrap; word-break: break-word; font-size: 0.85rem;
      margin: 0.35rem 0 0.75rem 0; }
.timeline { list-style: none; padding-left: 0; margin: 0.5rem 0;
            counter-reset: step; }
.timeline .event { display: flex; gap: 0.6rem; padding: 0.55rem 0.75rem;
                   border-radius: 4px; margin-bottom: 0.4rem;
                   border-left: 3px solid #ddd; background: #fafafa; }
.timeline .event.tool-call { border-left-color: #1565c0; background: #f1f7fd; }
.timeline .event.tool-return { border-left-color: #2e7d32; background: #f1f8f1; }
.timeline .event.text { border-left-color: #6a1b9a; background: #faf5fc; }
.step-num { font-family: ui-monospace, Menlo, monospace; font-size: 0.75rem;
            color: #888; font-weight: 600; min-width: 1.5rem; text-align: right;
            padding-top: 0.15rem; }
.event-body { flex: 1; min-width: 0; }
.event-header { display: flex; align-items: baseline; gap: 0.6rem;
                margin-bottom: 0.2rem; }
.event-kind { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em;
              color: #666; font-weight: 600; }
.tool-call .event-kind { color: #1565c0; }
.tool-return .event-kind { color: #2e7d32; }
.text .event-kind { color: #6a1b9a; }
.tool-name { font-family: ui-monospace, Menlo, monospace; font-weight: 600;
             color: #111; font-size: 0.85rem; }
.args, .result { font-size: 0.78rem; margin: 0.2rem 0 0 0; max-height: 18rem;
                 overflow: auto; }
.judge { margin-top: 0.5rem; padding: 0.5rem 0.75rem;
         background: #f3e5f5; border-radius: 4px; font-size: 0.9rem; }
.score { font-family: ui-monospace, Menlo, monospace; font-weight: 700; }
.failure { margin-top: 0.5rem; padding: 0.5rem 0.75rem;
           background: #ffebee; border-radius: 4px; color: #b71c1c; }
.muted { color: #666; font-size: 0.85rem; }
.markdown-body { background: #f5f5f5; padding: 0.75rem 1rem; border-radius: 4px;
                 font-size: 0.9rem; margin: 0.35rem 0 0.75rem 0; }
.markdown-body > *:first-child { margin-top: 0; }
.markdown-body > *:last-child { margin-bottom: 0; }
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
    margin: 0.75rem 0 0.4rem 0; font-weight: 600; line-height: 1.25; }
.markdown-body h1 { font-size: 1.2rem; }
.markdown-body h2 { font-size: 1.1rem; }
.markdown-body h3 { font-size: 1rem; }
.markdown-body p { margin: 0.4rem 0; }
.markdown-body ul, .markdown-body ol { margin: 0.4rem 0; padding-left: 1.5rem; }
.markdown-body li { margin: 0.15rem 0; }
.markdown-body li > ul, .markdown-body li > ol { margin: 0.1rem 0 0.3rem 0; }
.markdown-body ol > li { margin-top: 0.5rem; }
.markdown-body ol > li:first-child { margin-top: 0.15rem; }
.markdown-body code { background: #e8e8e8; padding: 0.05rem 0.3rem;
                      border-radius: 3px; font-size: 0.85em;
                      font-family: ui-monospace, Menlo, monospace; }
.markdown-body pre { background: #2d2d2d; color: #f5f5f5; padding: 0.75rem;
                     border-radius: 4px; overflow-x: auto; }
.markdown-body pre code { background: transparent; color: inherit; padding: 0; }
.markdown-body table { border-collapse: collapse; margin: 0.5rem 0;
                       font-size: 0.85rem; }
.markdown-body th, .markdown-body td { border: 1px solid #ccc;
                                       padding: 0.25rem 0.55rem; text-align: left; }
.markdown-body th { background: #eaeaea; font-weight: 600; }
.markdown-body blockquote { border-left: 3px solid #ccc; padding-left: 0.75rem;
                            color: #555; margin: 0.4rem 0; }
.markdown-body a { color: #1565c0; }
"""

_SCRIPT = """
function setAllCases(open) {
  document.querySelectorAll('details.case').forEach(d => { d.open = open; });
}
function renderMarkdown() {
  if (typeof marked === 'undefined') return;
  marked.setOptions({ gfm: true, breaks: false });
  document.querySelectorAll('.markdown-body[data-md]').forEach(el => {
    try {
      const md = JSON.parse(el.getAttribute('data-md') || '""');
      el.innerHTML = marked.parse(md || '');
    } catch (e) {
      el.textContent = el.getAttribute('data-md') || '';
    }
  });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderMarkdown);
} else {
  renderMarkdown();
}
"""


def render(results: list[CaseResult]) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    cases_html = "".join(_render_case(r) for r in results)

    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Agent eval report</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        "<h1>Agent eval report</h1>"
        f'<div class="summary">{passed} passed / {failed} failed of {total} cases — {timestamp}</div>'
        '<div class="controls">'
        '<button type="button" onclick="setAllCases(true)">Expand all</button>'
        '<button type="button" onclick="setAllCases(false)">Collapse all</button>'
        "</div>"
        f"{cases_html}"
        '<script src="https://cdn.jsdelivr.net/npm/marked@15.0.7/marked.min.js"></script>'
        f"<script>{_SCRIPT}</script>"
        "</body></html>"
    )
