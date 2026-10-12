"""SKILL.md follows the Agent Skills format (https://agentskills.io/specification), and the checker itself bites."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import ROOT, make_dir
from skillspec import check_skill

VALID = "---\nname: demo\ndescription: >\n  First line\n  second line.\nmetadata:\n  author: someone\n---\n\n# demo\n"


def make_skill(frontmatter: str, folder: str = "demo") -> Path:
    skill = make_dir() / folder
    skill.mkdir()
    (skill / "SKILL.md").write_text(frontmatter, encoding="utf-8")
    return skill


def front(**fields: str) -> str:
    base = {"name": "demo", "description": "does a thing"}
    base.update(fields)
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in base.items() if v is not None) + "---\n\n# demo\n"


def published_name() -> str:
    """The name install.sh links the skill under: the root has no stable folder name (clone dir differs per machine and CI)."""
    match = re.search(r'^NAME="([^"]+)"', (ROOT / "install.sh").read_text(encoding="utf-8"), re.M)
    assert match, "install.sh no longer declares NAME="
    return match.group(1)


class CheckerBitesTest(unittest.TestCase):
    def errors(self, text: str, folder: str = "demo") -> list:
        return check_skill(make_skill(text, folder))

    def test_a_valid_skill_with_a_folded_block_and_metadata_passes(self):
        self.assertEqual(self.errors(VALID), [])

    def test_a_field_outside_the_spec_fails(self):
        self.assertTrue(any("unexpected" in e for e in self.errors(front(version="1"))))

    def test_an_uppercase_name_fails(self):
        self.assertTrue(any("lowercase" in e for e in self.errors(front(name="Demo"))))

    def test_consecutive_hyphens_fail(self):
        self.assertTrue(any("consecutive" in e for e in self.errors(front(name="de--mo"), "de--mo")))

    def test_a_hyphen_at_the_edge_fails(self):
        self.assertTrue(any("hyphen" in e for e in self.errors(front(name="-demo"), "-demo")))

    def test_a_name_that_differs_from_the_folder_fails(self):
        self.assertTrue(any("does not match" in e for e in self.errors(VALID, "other")))

    def test_a_missing_description_fails(self):
        self.assertTrue(any("description" in e for e in self.errors(front(description=None))))

    def test_a_description_over_1024_chars_fails(self):
        self.assertTrue(any("1024" in e for e in self.errors(front(description="x" * 1025))))

    def test_a_compatibility_over_500_chars_fails(self):
        self.assertTrue(any("500" in e for e in self.errors(front(compatibility="x" * 501))))

    def test_a_file_without_frontmatter_fails(self):
        self.assertTrue(any("frontmatter" in e for e in self.errors("# demo\n")))

    def test_a_name_over_64_chars_fails(self):
        name = "a" * 65
        self.assertTrue(any("64" in e for e in self.errors(front(name=name), name)))


class RealSkillTest(unittest.TestCase):
    def test_the_skill_at_the_root_follows_the_spec_under_the_name_install_sh_publishes(self):
        self.assertEqual(check_skill(ROOT, published_name()), [])


if __name__ == "__main__":
    unittest.main()
