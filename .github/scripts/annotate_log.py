"""Publish the tail of a CI log as GitHub error annotations.

Annotations are readable through the REST API (check-run annotations) even where the
raw job logs are not, so failing steps stay diagnosable.
Usage: python .github/scripts/annotate_log.py LOGFILE TITLE
"""

import re
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def main() -> None:
    path, title = Path(sys.argv[1]), sys.argv[2]
    if not path.exists():
        print(f"::error title={title}::log file {path} was not written")
        return
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", "replace")
    else:
        text = raw.decode("utf-8-sig", "replace")
    lines = [ANSI.sub("", ln).rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip()][-240:]
    chunks = [lines[i:i + 60] for i in range(0, len(lines), 60)] or [["(empty log)"]]
    for k, chunk in enumerate(chunks, 1):
        msg = "\n".join(chunk).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title={title} ({k}/{len(chunks)})::{msg}")


if __name__ == "__main__":
    main()
