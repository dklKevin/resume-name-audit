import json

import pytest

from name_audit.materials import Materials, Name

NAMES = (
    Name("Ann Black", "Ann", "Black", "Black", "F", True),
    Name("Bea Black", "Bea", "Black", "Black", "F", False),
    Name("Cal Black", "Cal", "Black", "Black", "M", True),
    Name("Dan Black", "Dan", "Black", "Black", "M", False),
    Name("Eve White", "Eve", "White", "white", "F", True),
    Name("Fay White", "Fay", "White", "white", "F", False),
    Name("Gus White", "Gus", "White", "white", "M", True),
    Name("Hal White", "Hal", "White", "white", "M", False),
    Name("David Ryan", "David", "Ryan", "white", "M", False),
)

TEMPLATE = "{NAME}\nColumbus, OH | {EMAIL}\n\nEDUCATION\n{DEGREE_LINE}, 2018\n\nResume {ID}"


@pytest.fixture
def materials() -> Materials:
    return Materials(
        job_posting="Data Analyst at a store.",
        resumes={i: TEMPLATE.replace("{ID}", str(i)) for i in range(1, 6)},
        names=NAMES,
        degree_lines={"high": "B.S. Statistics, State U", "low": "A.A.S., Community College"},
    )


def screening(score: int, decision: str | None = None) -> str:
    decision = decision or ("ADVANCE" if score >= 60 else "REJECT")
    return json.dumps({"score": score, "decision": decision, "reason": "Fits the role."})
