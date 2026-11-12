"""Count first-party source in Git's tracked and untracked reviewable files."""

from collections import defaultdict
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".css": "CSS", ".html": "HTML",
}
EXCLUDED = {"node_modules", ".venv", "dist", "build", "coverage", "__pycache__"}


def source_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    )
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = Path(raw.decode("utf-8"))
        if path.suffix in LANGUAGE and not EXCLUDED.intersection(path.parts):
            full = ROOT / path
            if full.is_file():
                yield LANGUAGE[path.suffix], full


def main():
    totals = defaultdict(lambda: [0, 0])
    for language, path in source_files():
        data = path.read_bytes()
        totals[language][0] += len(data.decode("utf-8").splitlines())
        totals[language][1] += len(data)
    all_lines = sum(value[0] for value in totals.values())
    all_bytes = sum(value[1] for value in totals.values())
    for language, (lines, size) in sorted(totals.items()):
        print(f"{language:12} {lines:5} lines {size:7} bytes")
    print(f"Python share {totals['Python'][0] / all_lines:.1%} of lines; "
          f"{totals['Python'][1] / all_bytes:.1%} of bytes")


if __name__ == "__main__":
    main()
