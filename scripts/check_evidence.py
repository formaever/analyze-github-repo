#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def emit_report(checked, errors, max_errors):
    print(json.dumps({
        "ok": not errors,
        "checked": checked,
        "error_count": len(errors),
        "errors": errors[:max_errors],
        "truncated": len(errors) > max_errors,
    }, ensure_ascii=False, indent=2))


def local_path(value):
    if str(value).replace("\\", "/").startswith("//"):
        raise ValueError("只接受本地路径，不接受 UNC 或网络共享路径")
    return Path(value)


def validate_document(document):
    if not isinstance(document, dict):
        raise ValueError("JSON 顶层必须是对象")
    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims 必须是非空数组")

    ids = set()
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ValueError(f"第 {index} 条引用必须是对象")
        for field in ("id", "claim", "file"):
            if not isinstance(claim.get(field), str) or not claim[field].strip():
                raise ValueError(f"第 {index} 条引用的 {field} 必须是非空字符串")
        if claim["id"] in ids:
            raise ValueError(f"引用 id 重复: {claim['id']}")
        ids.add(claim["id"])
        for field in ("start_line", "end_line"):
            if type(claim.get(field)) is not int:
                raise ValueError(f"引用 {claim['id']} 的 {field} 必须是整数，不能是布尔值")
    return claims


def check_reference(root, claim, line_counts):
    filename = claim["file"]
    normalized = filename.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (relative.is_absolute() or PureWindowsPath(filename).drive
            or ".." in relative.parts or ":" in normalized or "\x00" in filename):
        return {
            "id": claim["id"],
            "code": "PATH_OUTSIDE_ROOT",
            "message": "file 必须是仓库内的相对路径，不能包含上级目录、驱动器或特殊路径",
        }

    try:
        target = root.joinpath(*relative.parts).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "id": claim["id"],
            "code": "FILE_READ_ERROR",
            "message": f"无法解析文件路径: {exc}",
        }
    if not target.is_relative_to(root):
        return {
            "id": claim["id"],
            "code": "PATH_OUTSIDE_ROOT",
            "message": "解析符号链接或目录链接后，文件位于仓库外",
        }

    start, end = claim["start_line"], claim["end_line"]
    if start < 1 or end < start:
        return {
            "id": claim["id"],
            "code": "INVALID_LINE_RANGE",
            "message": "行号必须从 1 开始，且 start_line 不能大于 end_line",
        }

    try:
        if not target.exists():
            return {
                "id": claim["id"],
                "code": "FILE_NOT_FOUND",
                "message": f"引用文件不存在: {filename}",
            }
        if not target.is_file():
            return {
                "id": claim["id"],
                "code": "NOT_A_FILE",
                "message": f"引用目标不是普通文件: {filename}",
            }
        if target not in line_counts:
            with target.open(encoding="utf-8-sig") as source:
                line_counts[target] = sum(1 for _ in source)
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "id": claim["id"],
            "code": "FILE_READ_ERROR",
            "message": f"无法按 UTF-8 读取引用文件: {exc}",
        }

    count = line_counts[target]
    if end > count:
        return {
            "id": claim["id"],
            "code": "LINE_OUT_OF_RANGE",
            "message": f"引用结束行为 {end}，但文件只有 {count} 行",
        }
    return None


def main(argv=None):
    parser = JsonArgumentParser(description="检查本地源码引用位置，不验证结论真假。")
    parser.add_argument("repo_root", help="本地源码根目录")
    parser.add_argument("evidence_json", help="包含 claims 数组的 UTF-8 JSON 文件")
    parser.add_argument("--max-errors", type=int, default=20, help="最多显示的错误数，默认 20")
    max_errors = 20
    try:
        args = parser.parse_args(argv)
        if args.max_errors < 1:
            raise ValueError("--max-errors 必须大于 0")
        max_errors = args.max_errors
        root = local_path(args.repo_root).resolve(strict=True)
        local_path(root)
        if not root.is_dir():
            raise ValueError("repo_root 必须是目录")
        evidence = local_path(args.evidence_json).resolve(strict=True)
        local_path(evidence)
        document = json.loads(evidence.read_text(encoding="utf-8-sig"))
        claims = validate_document(document)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        emit_report(0, [{"id": None, "code": "INPUT_ERROR", "message": str(exc)}], max_errors)
        return 2

    errors = []
    line_counts = {}
    exit_code = 0
    for claim in claims:
        error = check_reference(root, claim, line_counts)
        if error is not None:
            errors.append(error)
            exit_code = max(exit_code, 2 if error["code"] == "FILE_READ_ERROR" else 1)
    emit_report(len(claims), errors, max_errors)
    return exit_code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
