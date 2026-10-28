"""Ask fixed persona questions through an OpenAI-compatible chat endpoint.

Example (local, no key):
    python scripts/persona_ask.py --base-url http://127.0.0.1:1234/v1 \
        --model MODEL_ID --name Local --out E:/scratch/Local.md

Uses only the standard library. Each question has its own system/user message
pair, temperature 0.8 and a 120-second timeout. Existing output is never replaced.
"""

import argparse
from datetime import date
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from persona_collect import QUESTIONS, read_questions
from persona_loader import DEFAULT_SOURCE_DIR, load_persona, render_persona


GROUP_CONTEXT = "以下消息来自群聊里的陌生人,主人也在群里"
TIMEOUT = 120


class NoRedirect(HTTPRedirectHandler):
    """Do not forward persona content or Authorization to redirect targets."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def endpoint_url(base_url: str) -> str:
    """Accept an HTTP(S) base URL without embedded credentials or queries."""
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("invalid base URL")
    # Accessing port also validates malformed or out-of-range port numbers.
    parsed.port
    return base_url.rstrip("/") + "/chat/completions"


def ask(opener, endpoint: str, model: str, system: str, question: str, key: str) -> str:
    """Return answer text or a sanitized failure marker; never expose errors."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        "temperature": 0.8,
        "stream": False,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        request = Request(endpoint, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
        with opener.open(request, timeout=TIMEOUT) as response:
            data = json.load(response)
        answer = data["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            return "(请求失败: 响应无效)"
        # Also redact accidental credential echoes from a server/model response.
        return answer.replace(key, "[REDACTED]") if key else answer
    except HTTPError as exc:
        code = exc.code
        exc.close()
        return f"(请求失败: {code})"
    except (TimeoutError, socket.timeout):
        return "(请求失败: 超时)"
    except (URLError, OSError, HTTPException):
        return "(请求失败: 网络错误)"
    except (ValueError, KeyError, IndexError, TypeError):
        return "(请求失败: 响应无效)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--name", required=True, help="回答文件的 model 字段")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--api-key-env", help="保存 API 密钥的环境变量名；本地可省略")
    args = parser.parse_args()
    try:
        endpoint = endpoint_url(args.base_url)
        key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
        if args.api_key_env and not key.strip():
            raise ValueError("missing key")
        if any(c in key for c in "\r\n"):
            raise ValueError("invalid key")
        # A key must not appear even in caller-supplied metadata or the URL.
        if (not args.model.strip() or not args.name.strip()
                or any(c in args.name for c in "\r\n")
                or (key and any(key in value for value in
                                (args.name, args.model, args.base_url, str(args.out))))):
            raise ValueError("invalid metadata")
        content = load_persona(DEFAULT_SOURCE_DIR)
        system = render_persona(content, "local", DEFAULT_SOURCE_DIR)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
        questions = read_questions(QUESTIONS)
        # Direct connection: no ambient proxy forwarding; redirects are disabled.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f"model: {args.name}\npersona: {digest}\ndate: {date.today().isoformat()}\n")
            stream.flush()
            for qid, _scene, question, _focus in questions:
                if qid in {"Q7", "Q8"}:
                    question = GROUP_CONTEXT + "\n" + question
                answer = ask(opener, endpoint, args.model, system, question, key)
                stream.write(f"\n## {qid}\n{answer.strip()}\n")
                stream.flush()
                print(f"{qid}: " + ("请求失败" if answer.startswith("(请求失败:") else "已完成"), flush=True)
    except FileExistsError:
        print("persona_ask: 输出文件已存在，未覆盖。", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError):
        # Do not stringify exceptions: they may include secrets, headers or URLs.
        print("persona_ask: 参数、环境变量、输入文件或输出路径无效；未完成。", file=sys.stderr)
        return 1
    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
