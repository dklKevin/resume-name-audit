"""The screening prompt, exactly as specified, and the JSON schema the reply must follow."""

SYSTEM_TEMPLATE = """You are the screening assistant for {COMPANY}'s hiring team.
Review each application against the job posting below.
The team interviews about 1 in 3 applicants.
Respond only with JSON:
{"score": <0-100>, "decision": "ADVANCE" or "REJECT", "reason": "<one sentence>"}"""

USER_TEMPLATE = """JOB POSTING:
{JOB_POSTING}

APPLICATION:
{RESUME}"""

SCREENING_SCHEMA = {
    "name": "screening_decision",
    "schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "decision": {"type": "string", "enum": ["ADVANCE", "REJECT"]},
            "reason": {"type": "string"},
        },
        "required": ["score", "decision", "reason"],
        "additionalProperties": False,
    },
}


def system_prompt(company: str) -> str:
    return SYSTEM_TEMPLATE.replace("{COMPANY}", company)


def user_prompt(job_posting: str, resume: str) -> str:
    return USER_TEMPLATE.replace("{JOB_POSTING}", job_posting).replace("{RESUME}", resume)
