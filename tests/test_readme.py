"""The docs are what a new install reads: every link in them lands, the index covers every capability, and the simple guide is only prompts."""
from __future__ import annotations

import re
import unittest

from pathlib import Path

from helpers import ROOT

DOCS = ROOT / "docs"
SIMPLE = (DOCS / "instalacion.md").read_text(encoding="utf-8")
PAGES = [ROOT / "README.md", DOCS / "instalacion.md", DOCS / "instalacion-detallada.md", DOCS / "showcase.md", DOCS / "referencia.md"]


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    return {slug(m.group(2)) for m in re.finditer(r"^(#{1,6}) (.+)$", path.read_text(encoding="utf-8"), re.M)}


class ReadmeTest(unittest.TestCase):
    def test_every_relative_link_and_image_in_the_docs_lands_on_a_file_and_an_anchor(self):
        link = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
        for page in PAGES:
            for target in link.findall(page.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target):  # https:, mailto:
                    continue
                path, _, fragment = target.partition("#")
                dest = (page.parent / path).resolve() if path else page
                self.assertTrue(dest.exists(), f"{page.name} links to {target}, which does not exist")
                if fragment and dest.suffix == ".md":
                    self.assertIn(fragment, anchors(dest), f"{page.name} links to {target}: no such heading")

    def test_the_index_links_each_component_to_the_showcase_and_the_install_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        rows = [line for line in readme.splitlines() if line.startswith("| **`run-in-cursor`**") or line.startswith("| **`ric hook`**")]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIn("docs/showcase.md#", row)
            self.assertIn("docs/instalacion.md#", row)

    def test_the_index_names_every_ric_command_the_cli_has(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for command in ("ric run", "ric send", "ric quit", "--deny", "ric hook"):
            self.assertIn(command, readme)

    def test_the_simple_guide_has_only_prompts_no_shell_blocks(self):
        # it is for someone who talks to the agent: `ric` invocations live in Ran chips (images) and in the detailed guide
        self.assertEqual([block for block in SIMPLE.split("```")[1::2]], [], "the simple guide has no code blocks to run")


if __name__ == "__main__":
    unittest.main()
