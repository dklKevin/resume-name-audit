"""Load the study materials and fill resume placeholders."""

import csv
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .config import EMAIL_DOMAIN, MATERIALS

PLACEHOLDERS = ("{NAME}", "{EMAIL}", "{DEGREE_LINE}")
RESUME_FILE = re.compile(r"resume_(\d{2})\.txt")


@dataclass(frozen=True)
class Name:
    name: str
    first: str
    last: str
    race: str
    gender: str
    degree_swap: bool

    @property
    def group(self) -> str:
        return f"{self.race} {self.gender}"

    @property
    def email(self) -> str:
        return f"{self.first}.{self.last}@{EMAIL_DOMAIN}".lower()


@dataclass(frozen=True)
class Materials:
    job_posting: str
    resumes: dict[int, str]
    names: tuple[Name, ...]
    degree_lines: dict[str, str]

    def fill(self, resume_id: int, name: Name, degree_level: str) -> str:
        return fill(self.resumes[resume_id], name, self.degree_lines[degree_level])

    def name(self, full_name: str) -> Name:
        for n in self.names:
            if n.name == full_name:
                return n
        raise KeyError(full_name)


def fill(template: str, name: Name, degree_line: str) -> str:
    return (
        template.replace("{NAME}", name.name)
        .replace("{EMAIL}", name.email)
        .replace("{DEGREE_LINE}", degree_line)
    )


def load_names(path: Path) -> tuple[Name, ...]:
    with path.open() as fh:
        return tuple(
            Name(
                name=row["name"],
                first=row["first"],
                last=row["last"],
                race=row["race"],
                gender=row["gender"],
                degree_swap=row["degree_swap"] == "yes",
            )
            for row in csv.DictReader(fh)
        )


def load_resumes(folder: Path) -> dict[int, str]:
    resumes = {}
    for path in sorted(folder.glob("resume_*.txt")):
        match = RESUME_FILE.fullmatch(path.name)
        if match:
            resumes[int(match.group(1))] = path.read_text()
    return resumes


def load(root: Path = MATERIALS) -> Materials:
    return Materials(
        job_posting=(root / "job_posting.txt").read_text().strip(),
        resumes={k: v.strip() for k, v in load_resumes(root / "resumes").items()},
        names=load_names(root / "names.csv"),
        degree_lines=json.loads((root / "degree_lines.json").read_text()),
    )


@cache
def default() -> Materials:
    return load()
