"""Numbered-clause parser preserving original character offsets."""

import re

from covenants.schemas import Clause

HEADER = re.compile(r"(?m)^[ \t]*(?:#{1,6}[ \t]+)?(?P<id>\d+(?:\.\d+)+)[ \t]+(?P<heading>[^\r\n]+)")


def parse_clauses(text: str) -> list[Clause]:
    matches = list(HEADER.finditer(text))
    if not matches:
        raise ValueError("no numbered clauses found; expected headings such as '22.2 Leverage'")
    clauses = []
    seen = set()
    for index, match in enumerate(matches):
        clause_id = match.group("id")
        if clause_id in seen:
            raise ValueError(f"duplicate clause id: {clause_id}")
        seen.add(clause_id)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        clauses.append(Clause(clause_id=clause_id, heading=match.group("heading").strip(),
                              text=text[match.start():end], start=match.start(), end=end))
    return clauses

