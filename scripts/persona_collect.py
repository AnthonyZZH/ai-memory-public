"""Collect manual model answers into an offline Markdown comparison.

Usage: python scripts/persona_collect.py ANSWER_DIRECTORY [--out OUTPUT.md]
Answer format is documented in tests/persona/questions.md. Only the output file
is written. Its parent directory must exist; existing files are never replaced.
"""

import argparse
from dataclasses import dataclass
from datetime import date
import html
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "tests/persona/questions.md"
QUESTION_ID = re.compile(r"Q[1-9]\d*")
ANSWER_HEADING = re.compile(r"^##\s+(Q[1-9]\d*)\s*$")


@dataclass
class ModelAnswers:
    model: str
    persona: str
    date: str
    answers: dict[str, str]


def read_questions(path: Path) -> list[tuple[str, str, str, str]]:
    """Read ID, scene, question and review focus from the question table."""
    questions = []
    seen = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if not cells or not QUESTION_ID.fullmatch(cells[0]):
            continue
        if len(cells) != 4 or cells[0] in seen:
            raise ValueError(f"题目表格式错误或 ID 重复: {line}")
        seen.add(cells[0])
        questions.append(tuple(cell.replace(r"\|", "|") for cell in cells))
    if not questions:
        raise ValueError("题目表中没有题目")
    return questions


def read_answers(path: Path, known_ids: set[str]) -> ModelAnswers:
    """Parse required metadata and Q sections, preserving multiline answers."""
    metadata = {}
    sections = {}
    current = None
    fence = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        match = ANSWER_HEADING.fullmatch(line) if fence is None else None
        if match:
            current = match.group(1)
            if current not in known_ids or current in sections:
                raise ValueError(f"{path.name}: 未知或重复题号 {current}")
            sections[current] = []
            continue
        if current is None:
            if not line.strip():
                continue
            key, separator, value = line.partition(":")
            if not separator or key not in {"model", "persona", "date"} or key in metadata:
                raise ValueError(f"{path.name}: 回答前的元数据格式错误")
            metadata[key] = value.strip()
        else:
            sections[current].append(line)
            if fence_match:
                marker, tail = fence_match.groups()
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence) and not tail.strip():
                    fence = None
    if set(metadata) != {"model", "persona", "date"} or not all(metadata.values()):
        raise ValueError(f"{path.name}: 必须提供 model、persona、date")
    if not re.fullmatch(r"[0-9a-fA-F]{8}", metadata["persona"]):
        raise ValueError(f"{path.name}: persona 必须为 8 位十六进制哈希")
    date.fromisoformat(metadata["date"])
    return ModelAnswers(
        metadata["model"], metadata["persona"].lower(), metadata["date"],
        {qid: "\n".join(lines).strip() for qid, lines in sections.items()},
    )


def cell(text: str) -> str:
    """Keep pipes, newlines and HTML in answers from breaking table cells."""
    return html.escape(text, quote=False).replace("|", "&#124;").replace("\n", "<br>")


def render_comparison(questions, models: list[ModelAnswers]) -> str:
    """Render the mismatch warning, model hashes and per-question tables."""
    lines = []
    if len({model.persona for model in models}) > 1:
        lines += [
            "> **⚠ 警告：各模型 persona 哈希不一致，使用的人格版本不同；请勿直接据此判断模型一致性。**",
            "",
        ]
    lines += ["# 人格回答对照表", "", "| 模型 | persona 哈希 | 回答日期 |", "|---|---|---|"]
    for model in models:
        lines.append(f"| {cell(model.model)} | {model.persona} | {cell(model.date)} |")
    for qid, scene, question, focus in questions:
        lines += [
            "", f"## {qid} · {cell(scene)}", "",
            f"题目：{cell(question)}", "", f"看点：{cell(focus)}", "",
            "| " + " | ".join(f"{cell(m.model)}（persona: {m.persona}）" for m in models) + " |",
            "| " + " | ".join("---" for _ in models) + " |",
            "| " + " | ".join(cell(m.answers.get(qid) or "(缺)") for m in models) + " |",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answer_dir", type=Path, help="包含 <模型名>.md 回答文件的目录")
    parser.add_argument("--out", type=Path, help="输出路径；父目录须已存在，文件不得已存在")
    args = parser.parse_args()
    try:
        answer_dir = args.answer_dir.resolve()
        if not answer_dir.is_dir():
            raise ValueError(f"回答目录不存在: {answer_dir}")
        output = (args.out or ROOT / "cache" / f"persona-compare-{date.today().isoformat()}.md").resolve()
        if output.exists():
            raise ValueError(f"输出文件已存在，请用 --out 指定新文件: {output}")
        paths = sorted(answer_dir.glob("*.md"), key=lambda p: p.name.casefold())
        if not paths:
            raise ValueError("回答目录中没有 .md 文件")
        questions = read_questions(QUESTIONS)
        models = [read_answers(path, {q[0] for q in questions}) for path in paths]
        if len({model.model for model in models}) != len(models):
            raise ValueError("多个回答文件使用了相同的 model 名称")
        report = render_comparison(questions, models)
        # Exclusive creation also prevents overwriting an input file or symlink.
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"persona_collect: {exc}", file=sys.stderr)
        return 1
    print(f"已生成 {output}（{len(questions)} 题，{len(models)} 个模型）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
