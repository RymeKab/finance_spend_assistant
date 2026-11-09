"""
Reads the procurement policy and splits it into citable clauses.

Why this exists
---------------
Claude cites the policy by clause number (for example "3.1"). The server then
looks up the exact text of that clause in this store and shows it to the user.
The quote on screen therefore always comes from the policy file itself, never
from the model's memory or paraphrase.

How clauses are identified
--------------------------
The policy uses headings like "## 3. Approval Thresholds" and numbered paragraphs
like "3.1 Approval is evidenced by ...".

* Each numbered paragraph becomes a clause with that number ("3.1").
* Each section also gets a clause with its own number ("3"). It holds the text
  before the first numbered paragraph (for §3, the thresholds table). If a section
  has no such text, it holds the whole section instead.

The leading clause number is removed from the quoted text, because the UI already
shows it as a label. Otherwise the text is verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECTION_HEADING = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
NUMBERED_CLAUSE = re.compile(r"^(\d+\.\d+)\s+(.*)$", re.S)


@dataclass(frozen=True)
class Clause:
    clause_id: str  # "3" or "3.1"
    section_title: str  # "Approval Thresholds"
    text: str  # verbatim policy text (without the leading clause number)


@dataclass
class Policy:
    title: str
    document_line: str  # e.g. "**Document ID:** FIN-POL-014 · **Version:** 3.2 · ..."
    clauses: dict[str, Clause] = field(default_factory=dict)  # in document order
    # Sections that have text before their first numbered clause (e.g. §1, §3).
    intro_sections: set[str] = field(default_factory=set)

    def get(self, reference: str) -> Clause | None:
        """Find a clause from a loose reference such as '§3.1', 'section 3.1' or '3.1'."""
        return self.clauses.get(normalise_reference(reference))

    def prompt_text(self) -> str:
        """The policy as shown to Claude: every clause prefixed with a [§id] anchor to cite."""
        lines = [self.title, self.document_line, ""]
        current_section = None
        for clause in self.clauses.values():
            section = clause.clause_id.split(".")[0]
            if section != current_section:
                current_section = section
                lines.append(f"## {section}. {clause.section_title}")
            # Skip the whole-section copy when the section also has numbered clauses,
            # so Claude sees each sentence exactly once.
            is_section_copy = "." not in clause.clause_id and section not in self.intro_sections
            if is_section_copy and self._has_numbered(section):
                continue
            lines.append(f"[§{clause.clause_id}] {clause.text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _has_numbered(self, section: str) -> bool:
        return any(c.startswith(section + ".") for c in self.clauses)


def normalise_reference(reference: str) -> str:
    """'§ 3.1', 'Section 3.1', '3.1.' -> '3.1'."""
    cleaned = re.sub(r"(?i)section|§|clause", "", str(reference)).strip().rstrip(".")
    return re.sub(r"\s+", "", cleaned)


def load_policy(path: Path) -> Policy:
    """Parse the policy markdown file into a Policy object."""
    lines = path.read_text(encoding="utf-8").splitlines()

    title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("# ")), "Policy")
    document_line = next((ln.strip() for ln in lines if ln.startswith("**Document ID")), "")

    # 1. Group the lines into sections: number -> (title, list of paragraphs).
    sections: list[tuple[str, str, list[str]]] = []
    paragraph: list[str] = []

    def close_paragraph() -> None:
        if paragraph and sections:
            sections[-1][2].append("\n".join(paragraph).strip())
        paragraph.clear()

    for line in lines:
        heading = SECTION_HEADING.match(line)
        if heading:
            close_paragraph()
            sections.append((heading.group(1), heading.group(2), []))
        elif not line.strip():
            close_paragraph()
        else:
            paragraph.append(line)
    close_paragraph()

    # 2. Turn each section's paragraphs into clauses.
    policy = Policy(title=title, document_line=document_line)
    for number, section_title, paragraphs in sections:
        intro: list[str] = []
        numbered: list[Clause] = []
        for text in paragraphs:
            match = NUMBERED_CLAUSE.match(text)
            if match:
                numbered.append(Clause(match.group(1), section_title, match.group(2).strip()))
            elif not numbered:
                intro.append(text)
            else:
                # A paragraph following a numbered clause (none in this policy) stays with it.
                last = numbered.pop()
                numbered.append(Clause(last.clause_id, section_title, last.text + "\n\n" + text))

        if intro:
            policy.intro_sections.add(number)
            section_text = "\n\n".join(intro)
        else:
            section_text = "\n\n".join(f"{c.clause_id} {c.text}" for c in numbered)
        policy.clauses[number] = Clause(number, section_title, section_text)
        for clause in numbered:
            policy.clauses[clause.clause_id] = clause

    return policy
