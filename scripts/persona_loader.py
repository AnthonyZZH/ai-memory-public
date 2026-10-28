"""Render persona sources without writing files or using a network.

Examples::

    python scripts/persona_loader.py --target local
    python scripts/persona_loader.py --target local --with-source
    python scripts/persona_loader.py --target dsh --source-dir E:/scratch/persona

The source directory must contain persona.md and voice.md. The default is her/
beside scripts/, independent of the working directory. All targets fingerprint
the same cleaned Markdown: SHA-256 of its UTF-8 bytes, first eight hex digits.
Character count excludes Unicode whitespace, includes Markdown punctuation, and
excludes target wrappers and the fingerprint footer. Optional identity, traits,
expressions, recent relationship and pending hints extend the shared content.
The steward target references the core sources and includes these extensions.
Social callers must use load_persona(..., target='social') before rendering;
that path never reads relationship or pending sources.
By default, the final Chinese corner-quoted source annotation on each list item
is omitted. --with-source retains it. Quotes inside the item remain unchanged.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


HEADING = re.compile(r"^(#{1,6})\s+\S")
LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
SOURCE_SUFFIX = re.compile(r"\s*「[^「」\r\n]*」\s*$")
DEFAULT_SOURCE_DIR = Path(__file__).resolve().parent.parent / "her"
DEFAULT_MAX_CHARS = 12000
EXTENSION_TITLES = ('底线(只有主人能改)', '当前性格参数', '小千自己攒的常用说法', '最近相处摘要', '待批提示')


def optional_yaml(path):
    """Read optional owner/engine data; malformed files stop prompt generation."""
    if not path.exists():
        return {}
    import yaml
    text = path.read_text(encoding='utf-8-sig')
    try:
        if path.suffix == '.md':
            lines = text.splitlines()
            if not lines or lines[0].strip() != '---':
                return {}
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == '---')
            text = '\n'.join(lines[1:end])
        value = yaml.safe_load(text)
    except (ValueError, StopIteration, yaml.YAMLError) as exc:
        raise ValueError('人格扩展文件无效') from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('人格扩展应为对象')
    return value


def pending_changes(source_dir):
    """Expose only validated dimension/delta pairs; archives remain on disk."""
    traits_path = source_dir / 'personality.json'
    traits = json.loads(traits_path.read_text(encoding='utf-8'))['traits'] if traits_path.exists() else {}
    items = []
    for path in sorted((source_dir / 'evolution/proposals/pending').glob('*.json')):
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('status', 'pending') != 'pending':
            continue
        trait, delta = value.get('trait'), value.get('delta')
        if trait not in traits or type(delta) is not int or not delta:
            raise ValueError('待批提案维度或幅度无效')
        items.append((trait, delta))
    return items


def extensions(source_dir, *, social=False):
    lock = optional_yaml(source_dir / 'identity-lock.yaml')
    lines = []
    for key in ('identity', 'principles'):
        values = lock.get(key, []) or []
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError('身份锁条目无效')
        lines.extend('- ' + ' '.join(v.split()) for v in values if v.strip())
    identity = '\n'.join(lines)
    path = source_dir / 'personality.json'
    params = ''
    if path.exists():
        values = json.loads(path.read_text(encoding='utf-8'))['traits']
        if any(type(v['value']) is not int for v in values.values()):
            raise ValueError('性格参数无效')
        params = ' '.join(k + str(v['value']) for k, v in values.items())
        if params:
            params += ' (0-100)'
    path = source_dir / 'evolution/expressions.md'
    expressions = ''
    if path.exists():
        meta = optional_yaml(path)
        if 'entries' in meta:
            expressions = '\n'.join('- ' + ' '.join(v['text'].split()) for v in meta['entries'] if v['text'].strip())
        else:
            expressions = clean_markdown(path.read_text(encoding='utf-8'))
    # Social rendering must not even read owner relationship/pending files.
    if social:
        return [identity, params, expressions, '', '']
    path = source_dir / 'relationship.md'
    relationship = ''
    if path.exists():
        relationship = clean_markdown(path.read_text(encoding='utf-8'))
        relationship = relationship.split('## Relations', 1)[0]
        relationship = re.sub(r'<!--.*?-->', '', relationship, flags=re.S)
        relationship = '\n'.join(line for line in relationship.splitlines() if not HEADING.match(line)).strip()[-600:]
    pending = pending_changes(source_dir)
    reminder = ('有 ' + str(len(pending)) + ' 项性格变化等主人批准:' +
                '、'.join(k + ' ' + format(v, '+d') for k, v in pending) +
                ',下次和主人聊天时主动提一下') if pending else ''
    return [identity, params, expressions, relationship, reminder]


def clean_markdown(text: str, with_source: bool = False) -> str:
    """Remove metadata, all blockquote lines, placeholders and empty headings."""
    lines = text.lstrip("\ufeff").splitlines()
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() in {"---", "..."}:
                lines = lines[end + 1:]
                break
        else:
            raise ValueError("frontmatter 缺少结束分隔符")

    # Each heading owns a section. Keep ancestors of nonempty subsections too.
    sections = [{"level": 0, "heading": "", "body": [], "keep": False}]
    for line in lines:
        line = line.rstrip()
        if not with_source and LIST_ITEM.match(line):
            line = SOURCE_SUFFIX.sub("", line).rstrip()
        stripped = line.strip()
        if stripped == "-" or stripped.startswith(">"):
            continue
        match = HEADING.match(line)
        if match:
            sections.append({
                "level": len(match.group(1)), "heading": line,
                "body": [], "keep": False,
            })
        else:
            sections[-1]["body"].append(line)

    ancestors = []
    for index, section in enumerate(sections):
        while ancestors and sections[ancestors[-1]]["level"] >= section["level"]:
            ancestors.pop()
        ancestors.append(index)
        if any(line.strip() for line in section["body"]):
            for ancestor in ancestors:
                sections[ancestor]["keep"] = True

    blocks = []
    for section in sections:
        if section["keep"]:
            body = "\n".join(section["body"]).strip()
            block = "\n\n".join(
                part for part in (section["heading"], body) if part
            )
            if block:
                blocks.append(block)
    return "\n\n".join(blocks)


def load_persona(source_dir: Path, with_source: bool = False, max_chars: int = DEFAULT_MAX_CHARS, *, target: str = 'local') -> str:
    """Read both required sources and reject a completely empty persona."""
    parts = []
    for filename in ("persona.md", "voice.md"):
        path = source_dir / filename
        try:
            part = clean_markdown(path.read_text(encoding="utf-8-sig"), with_source)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"无法加载 {path}: {exc}") from exc
        if part:
            parts.append(part)
    if not parts:
        raise ValueError("人格内容为空：persona.md 和 voice.md 的所有小节均未填写")
    base = "\n\n".join(parts)
    try:
        extra = extensions(source_dir, social=target == 'social')
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, ImportError) as exc:
        raise ValueError('无法加载人格扩展文件') from exc
    def joined():
        return '\n\n'.join([base] + ['## ' + title + '\n\n' + body for title, body in zip(EXTENSION_TITLES, extra) if body])
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError('总长度上限必须为正整数')
    # Reserve enough for the largest of the three wrappers and footer digits;
    # the same content/hash must fit every target, including steward references.
    overhead = max(len(render_persona('', target, source_dir, with_source))
                   for target in ('local', 'dsh', 'steward')) + len(str(max_chars))
    content_limit = max_chars - overhead
    # Preserve identity, current parameters and pending notices. Trim recent
    # relationship first, then the oldest (last) expressions. Never cut identity.
    while len(joined()) > content_limit and extra[3]:
        excess = len(joined()) - content_limit
        extra[3] = extra[3][min(excess, len(extra[3])):].lstrip()
    while len(joined()) > content_limit and extra[2]:
        extra[2] = '\n'.join(extra[2].splitlines()[:-1]).rstrip()
    if len(joined()) > content_limit:
        raise ValueError('人格核心超过总长度上限，不能截断身份或底线')
    return joined()


def render_persona(
    content: str, target: str, source_dir: Path, with_source: bool = False,
) -> str:
    """Wrap the common content for an entry point, with a shared fingerprint."""
    if target == 'social' and any('\n\n## ' + title + '\n' in content for title in EXTENSION_TITLES[3:]):
        raise ValueError("social 渲染必须使用 load_persona(..., target='social')，不能传入主人上下文")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    count = sum(not character.isspace() for character in content)
    if target in ("local", "social"):
        output = "以下为人格与说话方式设定：\n\n" + content
    elif target == "dsh":
        output = "<persona>\n" + content + "\n</persona>"
    elif target == "steward":
        output = (
            "人格与说话方式以以下文件为准，按需读取；未填写部分不得自行补全：\n"
            f"- {source_dir / 'persona.md'}\n"
            f"- {source_dir / 'voice.md'}"
        )
        output += "\n读取时" + ("保留" if with_source else "去掉") + "条目末尾的「」出处标注。"
        offsets = [content.find('\n\n## ' + title + '\n') for title in EXTENSION_TITLES]
        offsets = [position for position in offsets if position >= 0]
        if offsets:
            output += content[min(offsets):]
    else:
        raise ValueError(f"未知入口: {target}")
    return f"{output}\n\n[persona sha256={digest} 字数={count}]"


def main() -> int:
    """Write only a complete rendering to stdout; report failures to stderr."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=("local", "dsh", "steward", "social"))
    parser.add_argument(
        "--with-source", action="store_true",
        help="保留条目末尾的「」出处标注（默认去掉）",
    )
    parser.add_argument(
        "--source-dir", type=Path, default=DEFAULT_SOURCE_DIR,
        help="包含 persona.md、voice.md 的目录（默认：仓库 her/）",
    )
    parser.add_argument('--max-chars', type=int, default=DEFAULT_MAX_CHARS,
                        help='包含入口包装和尾注的总上限，默认 12000 字符；优先截最近相处摘要')
    args = parser.parse_args()
    try:
        source_dir = args.source_dir.resolve()
        content = load_persona(source_dir, args.with_source, args.max_chars, target=args.target)
        output = render_persona(content, args.target, source_dir, args.with_source)
    except (OSError, ValueError) as exc:
        print(f"persona_loader: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
