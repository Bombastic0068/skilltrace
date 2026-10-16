import re

from llm_client import generate_json

ALLOWED_STATUSES = {
    "Demonstrated",
    "Not demonstrated in this scope",
    "Unclear",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
MAX_REQUIREMENTS = 8

GENERIC_REQUIREMENT_PATTERNS = (
    r"^git$",
    r"^github$",
    r"communication",
    r"teamwork",
    r"collaboration",
    r"code review",
    r"feedback",
    r"deadline",
    r"estimation",
    r"problem[- ]solving",
    r"ownership",
    r"soft skill",
    r"college",
    r"graduation",
    r"hours per week",
    r"documentation",
    r"self-review",
    r"asking questions",
)

MERGE_ALIASES = {
    "golang": "Go",
    "go (golang)": "Go",
    "go lang": "Go",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "restful apis": "REST APIs",
    "restful api": "REST APIs",
    "api development": "REST APIs",
    "apis": "REST APIs",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "sql queries": "SQL",
    "relational sql": "SQL",
    "unit tests": "Automated testing",
    "unit testing": "Automated testing",
    "writing tests": "Automated testing",
    "testing": "Automated testing",
    "test writing": "Automated testing",
    "auth": "Authentication",
    "authentication": "Authentication",
    "authorization": "Authentication",
    "authentication and authorization": "Authentication",
    "oauth": "Authentication",
    "oauth 2.0": "Authentication",
    "jwt": "Authentication",
    "background jobs": "Background jobs",
    "asynchronous workflows": "Background jobs",
    "queues": "Background jobs",
    "worker systems": "Background jobs",
    "docker": "Docker",
    "containerization": "Docker",
    "ci/cd": "CI/CD",
    "continuous integration": "CI/CD",
    "deployment": "CI/CD",
    "relational data modeling": "SQL",
    "relational data modelling": "SQL",
    "data modelling": "SQL",
    "data modeling": "SQL",
}


def _normalize_requirement(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    alias = MERGE_ALIASES.get(cleaned.lower())
    return alias or cleaned


def _is_generic(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in GENERIC_REQUIREMENT_PATTERNS)


def _mentions_testing(job_text: str) -> bool:
    return bool(
        re.search(
            r"\b(testing|unit tests?|qa|quality assurance|test automation|"
            r"automated testing|write tests|writing tests)\b",
            job_text,
            flags=re.IGNORECASE,
        )
    )


def extract_requirements(job_text: str) -> list[str]:
    """Send a job posting to the LLM and return up to 8 concrete technical requirements."""
    prompt = f"""
You extract hiring requirements from a job posting.

Return JSON only, in this shape:
{{
  "requirements": ["Go", "PostgreSQL", "REST APIs", "SQL"]
}}

Rules:
- Return at most {MAX_REQUIREMENTS} items.
- Include only concrete technical skills or technologies named in the posting.
- Prefer required skills over bonus skills.
- Merge duplicates and near-duplicates into one name (example: Golang and Go -> Go; REST APIs and API development -> REST APIs).
- Exclude generic items such as Git, GitHub, communication, teamwork, collaboration, code review, deadlines, estimation, and similar non-technical habits.
- Do not invent skills that are not in the posting.
- Keep specific technologies as their own items when they are named (Go, PostgreSQL, Redis, Docker).
- Keep transferable capabilities as their own items when they are named (REST APIs, SQL, Automated testing, Authentication, Background jobs, CI/CD).
- If the posting mentions testing, unit tests, QA, quality assurance, or test automation, always include "Automated testing".

Job posting:
{job_text}
""".strip()

    data = generate_json(prompt)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("requirements", [])
    else:
        items = []

    requirements: list[str] = []
    seen: set[str] = set()
    if _mentions_testing(job_text):
        requirements.append("Automated testing")
        seen.add("automated testing")

    for item in items:
        if isinstance(item, dict):
            text = str(item.get("requirement") or item.get("name") or "").strip()
        else:
            text = str(item).strip()
        text = _normalize_requirement(text)
        key = text.lower()
        if not text or key in seen or _is_generic(text):
            continue
        seen.add(key)
        requirements.append(text)
        if len(requirements) >= MAX_REQUIREMENTS:
            break
    return requirements


def assess_requirements(requirements: list[str], repo_files: list[dict]) -> list[dict]:
    """Assess each requirement against the provided repo files only."""
    if not requirements:
        return []

    file_blocks = []
    provided_paths = []
    for file in repo_files:
        path = file.get("path", "")
        content = file.get("content", "")
        provided_paths.append(path)
        file_blocks.append(f"FILE: {path}\n{content}")

    files_text = "\n\n".join(file_blocks) if file_blocks else "(no files provided)"
    path_list = "\n".join(f"- {path}" for path in provided_paths) or "- (none)"
    requirements_text = "\n".join(f"- {item}" for item in requirements)

    prompt = f"""
You compare a student's GitHub files against technical job requirements.

Return JSON only, in this shape:
{{
  "assessments": [
    {{
      "requirement": "REST APIs",
      "status": "Demonstrated",
      "confidence": "high",
      "evidence": [
        {{
          "path": "app.py",
          "snippet": "short quote copied from that file"
        }}
      ],
      "reason": "One sentence explaining the evidence found in the provided files."
    }}
  ]
}}

Status must be exactly one of:
- "Demonstrated"
- "Not demonstrated in this scope"
- "Unclear"

Confidence must be exactly one of: "high", "medium", "low".

How to decide status:
- Capability requirements (REST APIs, SQL, Automated testing, Authentication, Background jobs, CI/CD) count as Demonstrated if the code actually shows that capability, even with a different technology.
  Examples: Flask or FastAPI routes demonstrate REST APIs. sqlite3 or MySQL queries demonstrate SQL. pytest or unittest files demonstrate Automated testing.
- Specific technologies (PostgreSQL, Go, Redis, Docker, GORM, AWS) count as Demonstrated only if the files show that exact technology.
  Example: sqlite3 does not demonstrate PostgreSQL. Python/Flask does not demonstrate Go. A requirements.txt without redis does not demonstrate Redis.

Confidence:
- high: the files clearly show or clearly do not show the requirement.
- medium: related evidence exists but it is incomplete.
- low: the evidence is weak or the mapping is uncertain.

Strict rules:
- Only cite files from this provided list. Never invent file names or paths.
- Evidence snippets must be copied from the provided file contents.
- If a requirement is not shown in these files, use status "Not demonstrated in this scope".
- Never say the student lacks a skill, is unqualified, or cannot do something.
- Only say that no evidence was found in the analyzed files.
- Assess every requirement in the list, in the same order.

Provided file paths:
{path_list}

Requirements:
{requirements_text}

Provided files:
{files_text}
""".strip()

    data = generate_json(prompt)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("assessments") or data.get("results") or []
    else:
        rows = []

    allowed_paths = set(provided_paths)
    by_requirement = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        requirement = str(row.get("requirement", "")).strip()
        if not requirement:
            continue
        status = str(row.get("status", "Unclear")).strip()
        if status not in ALLOWED_STATUSES:
            status = "Unclear"
        confidence = str(row.get("confidence", "medium")).strip().lower()
        if confidence not in ALLOWED_CONFIDENCE:
            confidence = "medium"
        evidence = []
        for item in row.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if path not in allowed_paths:
                continue
            snippet = str(item.get("snippet", "")).strip()
            evidence.append({"path": path, "snippet": snippet})
        if status == "Demonstrated" and not evidence:
            status = "Unclear"
            confidence = "low"
        reason = str(row.get("reason", "")).strip()
        if status == "Not demonstrated in this scope" and not reason:
            reason = "No evidence for this requirement was found in the analyzed files."
        by_requirement[requirement.lower()] = {
            "requirement": requirement,
            "status": status,
            "confidence": confidence,
            "evidence": evidence,
            "reason": reason,
        }

    results = []
    for requirement in requirements:
        existing = by_requirement.get(requirement.lower())
        if existing:
            existing["requirement"] = requirement
            results.append(existing)
        else:
            results.append(
                {
                    "requirement": requirement,
                    "status": "Unclear",
                    "confidence": "low",
                    "evidence": [],
                    "reason": "No evidence assessment was returned for this requirement in the analyzed files.",
                }
            )
    return results
