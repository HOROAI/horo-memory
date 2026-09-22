from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import NoteCreate, utc_now
from .security import digest_bytes, safe_child, validate_id

SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class Vault:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace_root(self, workspace_id: str) -> Path:
        validate_id(workspace_id, "workspace_id")
        root = safe_child(self.root, workspace_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def write_note(self, note: NoteCreate) -> dict[str, Any]:
        if not SLUG.fullmatch(note.slug):
            raise ValueError("Invalid note slug")
        workspace_root = self.workspace_root(note.workspace_id)
        category_root = safe_child(workspace_root, note.category)
        category_root.mkdir(parents=True, exist_ok=True)
        path = safe_child(category_root, f"{note.slug}.md")

        frontmatter = {
            "title": note.title,
            "workspace": note.workspace_id,
            "category": note.category,
            "updated_at": utc_now(),
            **note.frontmatter,
        }
        lines = ["---"]
        for key, value in frontmatter.items():
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = json.dumps(value, ensure_ascii=False)
            lines.append(f"{key}: {rendered}")
        lines.extend(["---", "", f"# {note.title}", "", note.body.rstrip(), ""])
        content = "\n".join(lines).encode("utf-8")

        temporary = path.with_suffix(".md.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return {
            "relative_path": path.relative_to(self.root).as_posix(),
            "sha256": digest_bytes(content),
            "updated_at": frontmatter["updated_at"],
        }

    def search(self, workspace_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        root = self.workspace_root(workspace_id)
        terms = [term.lower() for term in query.split() if len(term) >= 2]
        matches: list[tuple[int, dict[str, Any]]] = []
        for path in root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score:
                matches.append(
                    (
                        score,
                        {
                            "source": "vault",
                            "path": path.relative_to(root).as_posix(),
                            "score": score,
                            "excerpt": _excerpt(text, terms),
                        },
                    )
                )
        matches.sort(key=lambda item: (-item[0], item[1]["path"]))
        return [item for _, item in matches[:limit]]


def _excerpt(text: str, terms: list[str], length: int = 420) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 100)
    excerpt = text[start : start + length].strip()
    return excerpt + ("…" if start + length < len(text) else "")
