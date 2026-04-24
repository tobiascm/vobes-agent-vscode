#!/usr/bin/env python3
"""Confluence Storage-XHTML ↔ annotated Markdown bridge.

Commands:
  storage2md <in.html> <out.md>     Convert Storage-XHTML → annotated Markdown
  md2storage <in.md> <out.html>     Convert annotated Markdown → Storage-XHTML
  prepare    --before X --after Y   Open VS Code diff + optional notify
  finalize   --input X --output Y   Convert edited MD → XHTML with integrity check

Uses only Python stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMOTICON_MAP = {
    "tick": "✅",
    "warning": "⚠️",
    "cross": "❌",
    "plus": "➕",
    "minus": "➖",
    "question": "❓",
    "info": "ℹ️",
    "light-on": "💡",
    "star_yellow": "⭐",
    "thumbs-up": "👍",
    "thumbs-down": "👎",
}

EMOTICON_REVERSE = {v: k for k, v in EMOTICON_MAP.items()}

# Known ac: tags that we convert to MD annotations
KNOWN_AC_TAGS = {
    "ac:task-list",
    "ac:task",
    "ac:task-id",
    "ac:task-uuid",
    "ac:task-status",
    "ac:task-body",
    "ac:emoticon",
    "ac:link",
}

KNOWN_RI_TAGS = {
    "ri:user",
    "ri:page",
}


# ===================================================================
# Storage → Markdown converter
# ===================================================================


class StorageToMarkdown(HTMLParser):
    """Convert Confluence Storage-Format XHTML to annotated Markdown."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []
        self.list_stack: list[str] = []  # 'ul' or 'ol'
        self.in_li = False
        self.li_buffer: list[str] = []
        self.in_strong = False
        self.in_a = False
        self.a_href = ""
        self.in_heading = ""
        self.heading_buffer: list[str] = []

        # Task tracking
        self.in_task_list = False
        self.in_task = False
        self.task_id = ""
        self.task_uuid = ""
        self.task_status = ""
        self.in_task_body = False
        self.task_body_buf: list[str] = []
        self.collecting_task_meta = ""  # 'id', 'uuid', 'status'

        # Raw passthrough for unknown ac: blocks
        self.raw_depth = 0
        self.raw_buffer: list[str] = []
        self.raw_tag_stack: list[str] = []

        # Suppress nested list rendering inside ac:task-body (handled separately)
        self.suppress_list = 0

    # -- helpers --

    def _indent(self) -> str:
        depth = max(0, len(self.list_stack) - 1)
        return "  " * depth

    def _flush_li(self):
        if self.li_buffer:
            text = "".join(self.li_buffer).strip()
            if text:
                indent = self._indent()
                self.output.append(f"{indent}- {text}\n")
            self.li_buffer = []

    def _is_raw_mode(self) -> bool:
        return self.raw_depth > 0

    def _start_raw(self, tag, attrs):
        """Enter passthrough mode for an unknown ac:/ri: block."""
        if self.raw_depth == 0:
            self._flush_li()
            self.raw_buffer = []
        self.raw_depth += 1
        self.raw_tag_stack.append(tag)
        attrs_str = "".join(f' {k}="{v}"' for k, v in attrs)
        self.raw_buffer.append(f"<{tag}{attrs_str}>")

    def _end_raw(self, tag):
        self.raw_buffer.append(f"</{tag}>")
        self.raw_depth -= 1
        if self.raw_tag_stack:
            self.raw_tag_stack.pop()
        if self.raw_depth == 0:
            raw_html = "".join(self.raw_buffer)
            indent = self._indent() if self.list_stack else ""
            self.output.append(f"{indent}<!-- confluence:raw -->\n")
            self.output.append(f"{indent}{raw_html}\n")
            self.output.append(f"{indent}<!-- /confluence:raw -->\n")
            self.raw_buffer = []

    # -- parser callbacks --

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        # If in raw mode, collect everything
        if self._is_raw_mode():
            attrs_str = "".join(f' {k}="{v}"' for k, v in attrs)
            self.raw_buffer.append(f"<{tag_lower}{attrs_str}>")
            if tag_lower.startswith(("ac:", "ri:")):
                self.raw_depth += 1
                self.raw_tag_stack.append(tag_lower)
            return

        # --- Known ac: / ri: handling ---
        if tag_lower == "ac:task-list":
            self.in_task_list = True
            return
        if tag_lower == "ac:task":
            self.in_task = True
            self.task_id = ""
            self.task_uuid = ""
            self.task_status = ""
            self.task_body_buf = []
            return
        if tag_lower == "ac:task-id":
            self.collecting_task_meta = "id"
            return
        if tag_lower == "ac:task-uuid":
            self.collecting_task_meta = "uuid"
            return
        if tag_lower == "ac:task-status":
            self.collecting_task_meta = "status"
            return
        if tag_lower == "ac:task-body":
            self.in_task_body = True
            self.task_body_buf = []
            return

        if tag_lower == "ac:emoticon":
            name = attrs_dict.get("ac:name", "")
            emoji = EMOTICON_MAP.get(name, f":{name}:")
            target = self.task_body_buf if self.in_task_body else self.li_buffer
            target.append(emoji)
            return

        if tag_lower == "ac:link":
            # ac:link wraps ri:user or ri:page — just pass through
            return

        if tag_lower == "ri:user":
            userkey = attrs_dict.get("ri:userkey", "")
            text = f"@[userkey:{userkey}]"
            target = self.task_body_buf if self.in_task_body else self.li_buffer
            target.append(text)
            return

        if tag_lower == "ri:page":
            title = attrs_dict.get("ri:content-title", "")
            text = f"[[{title}]]"
            target = self.task_body_buf if self.in_task_body else self.li_buffer
            target.append(text)
            return

        # Unknown ac: or ri: → raw passthrough
        if tag_lower.startswith(("ac:", "ri:")):
            if tag_lower not in KNOWN_AC_TAGS and tag_lower not in KNOWN_RI_TAGS:
                self._start_raw(tag_lower, attrs)
                return

        # --- Standard HTML ---
        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_li()
            level = int(tag_lower[1])
            self.in_heading = "#" * level
            self.heading_buffer = []
            return

        if tag_lower == "ul":
            if self.in_task_body:
                self.suppress_list += 1
                return
            self._flush_li()
            self.list_stack.append("ul")
            return

        if tag_lower == "ol":
            if self.in_task_body:
                self.suppress_list += 1
                return
            self._flush_li()
            self.list_stack.append("ol")
            return

        if tag_lower == "li":
            if self.suppress_list:
                return
            self._flush_li()
            self.in_li = True
            self.li_buffer = []
            return

        if tag_lower == "strong" or tag_lower == "b":
            self.in_strong = True
            target = self.task_body_buf if self.in_task_body else (
                self.heading_buffer if self.in_heading else self.li_buffer
            )
            target.append("**")
            return

        if tag_lower == "em" or tag_lower == "i":
            target = self.task_body_buf if self.in_task_body else (
                self.heading_buffer if self.in_heading else self.li_buffer
            )
            target.append("*")
            return

        if tag_lower == "a":
            self.in_a = True
            self.a_href = attrs_dict.get("href", "")
            return

        if tag_lower == "time":
            dt = attrs_dict.get("datetime", "")
            text = f"(bis {dt})"
            target = self.task_body_buf if self.in_task_body else self.li_buffer
            target.append(text)
            return

        if tag_lower == "br":
            target = self.task_body_buf if self.in_task_body else self.li_buffer
            target.append("  \n")
            return

        if tag_lower == "span":
            # skip style spans
            return

        if tag_lower == "p":
            return

    def handle_endtag(self, tag):
        tag_lower = tag.lower()

        # Raw mode
        if self._is_raw_mode():
            if tag_lower.startswith(("ac:", "ri:")):
                self._end_raw(tag_lower)
            else:
                self.raw_buffer.append(f"</{tag_lower}>")
            return

        if tag_lower == "ac:task-list":
            self.in_task_list = False
            return

        if tag_lower == "ac:task":
            # Emit task as markdown
            check = "x" if self.task_status == "complete" else " "
            body = "".join(self.task_body_buf).strip()
            annotation = f"<!-- task id={self.task_id} uuid={self.task_uuid} status={self.task_status} -->"
            indent = self._indent()
            self.output.append(f"{indent}- [{check}] {body} {annotation}\n")
            self.in_task = False
            return

        if tag_lower == "ac:task-id":
            self.collecting_task_meta = ""
            return
        if tag_lower == "ac:task-uuid":
            self.collecting_task_meta = ""
            return
        if tag_lower == "ac:task-status":
            self.collecting_task_meta = ""
            return
        if tag_lower == "ac:task-body":
            self.in_task_body = False
            return

        if tag_lower == "ac:link":
            return
        if tag_lower in ("ac:emoticon", "ri:user", "ri:page"):
            return

        # Unknown ac:/ri: end — shouldn't reach here if raw mode handled it
        if tag_lower.startswith(("ac:", "ri:")):
            return

        # Standard HTML
        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = "".join(self.heading_buffer).strip()
            self.output.append(f"\n{self.in_heading} {text}\n\n")
            self.in_heading = ""
            self.heading_buffer = []
            return

        if tag_lower == "ul":
            if self.suppress_list:
                self.suppress_list -= 1
                return
            self._flush_li()
            if self.list_stack:
                self.list_stack.pop()
            return

        if tag_lower == "ol":
            if self.suppress_list:
                self.suppress_list -= 1
                return
            self._flush_li()
            if self.list_stack:
                self.list_stack.pop()
            return

        if tag_lower == "li":
            if self.suppress_list:
                return
            self._flush_li()
            self.in_li = False
            return

        if tag_lower in ("strong", "b"):
            self.in_strong = False
            target = self.task_body_buf if self.in_task_body else (
                self.heading_buffer if self.in_heading else self.li_buffer
            )
            target.append("**")
            return

        if tag_lower in ("em", "i"):
            target = self.task_body_buf if self.in_task_body else (
                self.heading_buffer if self.in_heading else self.li_buffer
            )
            target.append("*")
            return

        if tag_lower == "a":
            self.in_a = False
            self.a_href = ""
            return

        if tag_lower == "time":
            return

        if tag_lower in ("span", "p", "br"):
            return

    def handle_data(self, data):
        if self._is_raw_mode():
            self.raw_buffer.append(data)
            return

        # Task meta collection
        if self.collecting_task_meta == "id":
            self.task_id = data.strip()
            return
        if self.collecting_task_meta == "uuid":
            self.task_uuid = data.strip()
            return
        if self.collecting_task_meta == "status":
            self.task_status = data.strip()
            return

        if self.in_task_body:
            self.task_body_buf.append(data)
            return

        if self.in_heading:
            self.heading_buffer.append(data)
            return

        if self.in_a and self.a_href:
            # Emit markdown link
            target = self.li_buffer
            target.append(f"[{data}]({self.a_href})")
            self.in_a = False  # consumed
            return

        if self.list_stack or self.in_li:
            self.li_buffer.append(data)
            return

        # Top-level text (outside lists)
        stripped = data.strip()
        if stripped:
            self.output.append(stripped + "\n")

    def handle_entityref(self, name):
        char_map = {"amp": "&", "lt": "<", "gt": ">", "nbsp": " ", "quot": '"'}
        ch = char_map.get(name, f"&{name};")
        self.handle_data(ch)

    def handle_charref(self, name):
        try:
            if name.startswith("x"):
                ch = chr(int(name[1:], 16))
            else:
                ch = chr(int(name))
        except ValueError:
            ch = f"&#{name};"
        self.handle_data(ch)

    def get_result(self) -> str:
        self._flush_li()
        return "".join(self.output).strip() + "\n"


def storage2md(html: str) -> str:
    """Convert Confluence Storage-Format XHTML to annotated Markdown."""
    parser = StorageToMarkdown()
    parser.feed(html)
    return parser.get_result()


# ===================================================================
# Markdown → Storage converter
# ===================================================================

# Regex patterns for MD → XHTML
RE_TASK = re.compile(
    r"^(\s*)-\s*\[([ xX])\]\s*(.*?)\s*"
    r"(?:<!--\s*task\s+id=(\S+)\s+uuid=(\S+)\s+status=(\S+)\s*-->)?\s*$"
)
RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
RE_LIST_ITEM = re.compile(r"^(\s*)-\s+(.*)")
RE_RAW_START = re.compile(r"^\s*<!--\s*confluence:raw\s*-->\s*$")
RE_RAW_END = re.compile(r"^\s*<!--\s*/confluence:raw\s*-->\s*$")
RE_USERKEY = re.compile(r"@\[userkey:([^\]]+)\]")
RE_PAGE_LINK = re.compile(r"\[\[([^\]]+)\]\]")
RE_TIME = re.compile(r"\(bis (\d{4}-\d{2}-\d{2})\)")
RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")

_NEXT_TASK_ID = 100  # auto-increment for new tasks


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_to_xhtml(text: str) -> str:
    """Convert inline MD annotations back to Storage-Format XHTML."""
    result = text

    # Emoticons (reverse map)
    for emoji, name in EMOTICON_REVERSE.items():
        result = result.replace(emoji, f'<ac:emoticon ac:name="{name}"></ac:emoticon>')

    # User references
    def _user_repl(m):
        return (
            f'<ac:link><ri:user ri:userkey="{m.group(1)}"></ri:user></ac:link>'
        )
    result = RE_USERKEY.sub(_user_repl, result)

    # Page links
    def _page_repl(m):
        return (
            f'<ac:link><ri:page ri:content-title="{_escape_html(m.group(1))}"></ri:page></ac:link>'
        )
    result = RE_PAGE_LINK.sub(_page_repl, result)

    # Time
    def _time_repl(m):
        return f'<time datetime="{m.group(1)}"></time>'
    result = RE_TIME.sub(_time_repl, result)

    # Markdown images → ac:image with ri:attachment (basename only)
    def _img_repl(m):
        fname = m.group(2).rsplit("/", 1)[-1]
        return f'<ac:image ac:width="800"><ri:attachment ri:filename="{_escape_html(fname)}" /></ac:image>'
    result = RE_MD_IMAGE.sub(_img_repl, result)

    # Markdown links
    def _link_repl(m):
        return f'<a href="{_escape_html(m.group(2))}">{_escape_html(m.group(1))}</a>'
    result = RE_MD_LINK.sub(_link_repl, result)

    # Bold
    result = RE_BOLD.sub(r"<strong>\1</strong>", result)

    # Italic (simple)
    result = RE_ITALIC.sub(r"<em>\1</em>", result)

    return result


def md2storage(md: str) -> str:
    """Convert annotated Markdown back to Confluence Storage-Format XHTML."""
    global _NEXT_TASK_ID

    lines = md.split("\n")
    output: list[str] = []
    i = 0

    # Track list nesting
    open_lists: list[int] = []  # indent levels
    in_task_list = False
    pending_tasks: list[str] = []

    def _close_lists_to(target_depth: int):
        nonlocal in_task_list
        if in_task_list and pending_tasks:
            _flush_tasks()
        while open_lists and open_lists[-1] >= target_depth:
            open_lists.pop()
            output.append("</li></ul>")

    def _flush_tasks():
        nonlocal in_task_list
        if pending_tasks:
            output.append("<ac:task-list>\n")
            output.extend(pending_tasks)
            output.append("</ac:task-list>")
            pending_tasks.clear()
        in_task_list = False

    while i < len(lines):
        line = lines[i]

        # Raw passthrough block
        if RE_RAW_START.match(line):
            raw_lines = []
            i += 1
            while i < len(lines) and not RE_RAW_END.match(lines[i]):
                raw_lines.append(lines[i])
                i += 1
            i += 1  # skip end marker
            output.append("".join(raw_lines))
            continue

        # Empty line
        if not line.strip():
            if in_task_list:
                _flush_tasks()
            i += 1
            continue

        # Heading
        m_heading = RE_HEADING.match(line)
        if m_heading:
            _close_lists_to(0)
            level = len(m_heading.group(1))
            text = _inline_to_xhtml(m_heading.group(2).strip())
            output.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Task item
        m_task = RE_TASK.match(line)
        if m_task:
            indent = len(m_task.group(1))
            checked = m_task.group(2).lower() == "x"
            body_text = m_task.group(3)
            task_id = m_task.group(4) or str(_NEXT_TASK_ID)
            task_uuid = m_task.group(5) or ""
            status = m_task.group(6) or ("complete" if checked else "incomplete")

            if not m_task.group(4):
                _NEXT_TASK_ID += 1
            if not task_uuid:
                import uuid as _uuid
                task_uuid = str(_uuid.uuid4())

            body_xhtml = _inline_to_xhtml(body_text)

            task_xml = (
                f"<ac:task>\n"
                f"<ac:task-id>{task_id}</ac:task-id>\n"
                f"<ac:task-uuid>{task_uuid}</ac:task-uuid>\n"
                f"<ac:task-status>{status}</ac:task-status>\n"
                f"<ac:task-body>{body_xhtml}</ac:task-body>\n"
                f"</ac:task>\n"
            )
            pending_tasks.append(task_xml)
            in_task_list = True
            i += 1
            continue

        # Regular list item
        m_li = RE_LIST_ITEM.match(line)
        if m_li:
            if in_task_list:
                _flush_tasks()

            indent = len(m_li.group(1))
            text = _inline_to_xhtml(m_li.group(2).strip())

            # Determine nesting
            if not open_lists:
                output.append("<ul>")
                open_lists.append(indent)
            elif indent > open_lists[-1]:
                output.append("<ul>")
                open_lists.append(indent)
            else:
                # Close deeper lists (all levels with indent > current)
                while open_lists and open_lists[-1] > indent:
                    open_lists.pop()
                    output.append("</li></ul>")
                if open_lists and open_lists[-1] == indent:
                    output.append("</li>")
                else:
                    # Returning to a shallower-than-stack indent that isn't on the stack
                    output.append("<ul>")
                    open_lists.append(indent)

            output.append(f"<li>{text}")
            i += 1
            continue

        # Plain text: continuation of previous list item (inside list) or paragraph (outside)
        if in_task_list:
            _flush_tasks()
        text = _inline_to_xhtml(line.strip())
        if text:
            if open_lists:
                output.append(f"<br/>{text}")
            else:
                output.append(f"<p>{text}</p>")
        i += 1

    # Close remaining
    if in_task_list:
        _flush_tasks()
    _close_lists_to(0)

    return "\n".join(output)


# ===================================================================
# Macro counting for integrity check
# ===================================================================

def _count_macros(html: str) -> dict[str, int]:
    """Count ac: macro occurrences in XHTML."""
    counts: dict[str, int] = {}
    for m in re.finditer(r"<(ac:\w[\w-]*)", html):
        tag = m.group(1)
        counts[tag] = counts.get(tag, 0) + 1
    return counts


# ===================================================================
# CLI commands
# ===================================================================

def cmd_storage2md(args):
    html = Path(args.input).read_text(encoding="utf-8")
    md = storage2md(html)
    Path(args.output).write_text(md, encoding="utf-8")
    print(json.dumps({"input": args.input, "output": args.output, "lines": md.count("\n")}))


def cmd_md2storage(args):
    md = Path(args.input).read_text(encoding="utf-8")
    html = md2storage(md)
    Path(args.output).write_text(html, encoding="utf-8")
    print(json.dumps({"input": args.input, "output": args.output, "bytes": len(html)}))


def cmd_prepare(args):
    # 1. Convert before.html → before.md
    html = Path(args.before).read_text(encoding="utf-8")
    before_md = storage2md(html)
    before_path = Path(args.before).with_suffix(".md")
    # Place beside --after for easy diff
    before_dir = Path(args.after).parent
    before_md_path = before_dir / (Path(args.before).stem + "_before.md")
    before_md_path.write_text(before_md, encoding="utf-8")

    # 2. Ensure after file exists (copy before_md as starting point if not)
    after_path = Path(args.after)
    if not after_path.exists():
        after_path.write_text(before_md, encoding="utf-8")

    # 3. Open VS Code diff (Windows has only code.cmd; POSIX has code)
    code_bin = shutil.which("code.cmd") or shutil.which("code")
    if code_bin:
        subprocess.Popen(
            [code_bin, "--diff", str(before_md_path), str(after_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        print("warn: VS Code CLI (code/code.cmd) not found in PATH — open diff manually.", file=sys.stderr)

    # 4. Notify
    if args.notify:
        notify_script = Path(__file__).parent / "hooks" / "notify.ps1"
        if notify_script.exists():
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(notify_script),
                    "-Status",
                    "done",
                    "-Message",
                    args.notify,
                    "-Title",
                    "Confluence Review",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    result = {
        "before_md": str(before_md_path),
        "after_md": str(after_path),
        "diff_opened": True,
    }
    print(json.dumps(result))


def cmd_finalize(args):
    md = Path(args.input).read_text(encoding="utf-8")
    html = md2storage(md)

    # Integrity check
    macro_result = {"output": args.output, "bytes": len(html)}
    if args.base:
        base_html = Path(args.base).read_text(encoding="utf-8")
        base_counts = _count_macros(base_html)
        result_counts = _count_macros(html)
        macro_result["macro_count_base"] = base_counts
        macro_result["macro_count_result"] = result_counts

        # Check for significant loss
        for tag, count in base_counts.items():
            r_count = result_counts.get(tag, 0)
            if r_count < count:
                macro_result.setdefault("warnings", []).append(
                    f"{tag}: {count} → {r_count}"
                )

        if args.strict and macro_result.get("warnings"):
            print(json.dumps(macro_result))
            sys.exit(1)

    Path(args.output).write_text(html, encoding="utf-8")
    print(json.dumps(macro_result))


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Confluence Storage ↔ Markdown bridge")
    sub = parser.add_subparsers(dest="command")

    # storage2md
    p1 = sub.add_parser("storage2md", help="Convert Storage-XHTML → Markdown")
    p1.add_argument("input", help="Input .html file")
    p1.add_argument("output", help="Output .md file")

    # md2storage
    p2 = sub.add_parser("md2storage", help="Convert Markdown → Storage-XHTML")
    p2.add_argument("input", help="Input .md file")
    p2.add_argument("output", help="Output .html file")

    # prepare
    p3 = sub.add_parser("prepare", help="Open diff + notify for review")
    p3.add_argument("--before", required=True, help="Original Storage-XHTML file")
    p3.add_argument("--after", required=True, help="Path for the after-MD file")
    p3.add_argument("--notify", help="Notification message")

    # finalize
    p4 = sub.add_parser("finalize", help="Convert edited MD → XHTML")
    p4.add_argument("--input", required=True, help="Edited .md file")
    p4.add_argument("--output", required=True, help="Output .html file")
    p4.add_argument("--base", help="Original .html for integrity check")
    p4.add_argument("--strict", action="store_true", help="Exit 1 on macro loss")

    args = parser.parse_args()
    if args.command == "storage2md":
        cmd_storage2md(args)
    elif args.command == "md2storage":
        cmd_md2storage(args)
    elif args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "finalize":
        cmd_finalize(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
