from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from analyzer import assess_requirements, extract_requirements
from github_client import get_latest_commit, github_blob_url, list_code_files, parse_github_url

BASE_DIR = Path(__file__).resolve().parent
JOB_FILE = BASE_DIR / "job.txt"
DEFAULT_REPO_URL = "https://github.com/Bombastic0068/student-backend-demo"

app = FastAPI(title="SkillTrace")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class AnalyzeRequest(BaseModel):
    job_link: str = ""
    job_text: str = Field(min_length=1)
    repo_url: str = Field(min_length=1)


def _default_job_text() -> str:
    if JOB_FILE.exists():
        return JOB_FILE.read_text(encoding="utf-8")
    return ""


def _default_job_link(job_text: str) -> str:
    first_line = job_text.strip().splitlines()[0] if job_text.strip() else ""
    if first_line.startswith("http://") or first_line.startswith("https://"):
        return first_line.strip()
    return ""


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "could not parse" in lowered:
        return "That GitHub repo URL looks invalid. Use a link like https://github.com/owner/repo."
    if "not found" in lowered or "404" in lowered:
        return "That GitHub repo could not be found. Check the URL and try again."
    if "token" in lowered or "401" in lowered:
        return "GitHub access failed. Check GITHUB_TOKEN in your .env file."
    if "rate limit" in lowered or "403" in lowered:
        return "GitHub rate-limited the request. Wait a moment and try again."
    if "gemini" in lowered or "llm" in lowered or "503" in lowered or "unavailable" in lowered:
        return "The analysis service is busy or failed. Please try again in a moment."
    if "no analyzable" in lowered or "empty" in lowered:
        return "This GitHub repo has no analyzable code files."
    return "Something went wrong while analyzing. Please check the repo URL and try again."


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    job_text = _default_job_text()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "job_text": job_text,
            "job_link": _default_job_link(job_text),
            "repo_url": DEFAULT_REPO_URL,
        },
    )


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    job_text = payload.job_text.strip()
    repo_url = payload.repo_url.strip()
    job_link = payload.job_link.strip()

    if not job_text:
        raise HTTPException(status_code=400, detail="Paste the job posting text before analyzing.")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Enter a GitHub repo URL before analyzing.")

    try:
        parse_github_url(repo_url)
        commit = get_latest_commit(repo_url)
        files = list_code_files(repo_url)
        if not files:
            raise HTTPException(
                status_code=400,
                detail="This GitHub repo has no analyzable code files.",
            )
        requirements = extract_requirements(job_text)
        assessments = assess_requirements(requirements, files)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc)) from exc

    results = []
    for row in assessments:
        evidence = []
        for item in row.get("evidence") or []:
            path = item.get("path", "")
            evidence.append(
                {
                    "path": path,
                    "snippet": item.get("snippet", ""),
                    "url": github_blob_url(repo_url, commit["sha"], path),
                }
            )
        results.append(
            {
                "requirement": row["requirement"],
                "status": row["status"],
                "confidence": row.get("confidence", "medium"),
                "evidence": evidence,
                "reason": row["reason"],
            }
        )

    return {
        "job_link": job_link,
        "commit_sha": commit["sha"],
        "commit_message": commit.get("short_message", ""),
        "files_analyzed": [file["path"] for file in files],
        "assessments": results,
    }
