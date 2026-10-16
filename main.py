from pathlib import Path

from analyzer import assess_requirements, extract_requirements
from github_client import get_latest_commit, list_code_files

REPO_URL = "https://github.com/Bombastic0068/student-backend-demo"
JOB_FILE = Path(__file__).with_name("job.txt")


def _print_table(assessments: list[dict]) -> None:
    req_width = max([len("Requirement")] + [len(row["requirement"]) for row in assessments] or [11])
    status_width = max(
        [len("Status")] + [len(row["status"]) for row in assessments] or [6]
    )
    req_width = min(req_width, 28)
    status_width = min(status_width, 32)

    header = (
        f"{'Requirement':<{req_width}}  "
        f"{'Status':<{status_width}}  "
        f"{'Confidence':<10}  Evidence"
    )
    print(header)
    print("-" * len(header))

    for row in assessments:
        evidence_paths = ", ".join(item["path"] for item in row["evidence"]) or "—"
        print(
            f"{row['requirement'][:req_width]:<{req_width}}  "
            f"{row['status']:<{status_width}}  "
            f"{row.get('confidence', '—'):<10}  "
            f"{evidence_paths}"
        )

    print()
    print("Details")
    print("-" * 60)
    for row in assessments:
        print(f"Requirement: {row['requirement']}")
        print(f"Status: {row['status']}")
        print(f"Confidence: {row.get('confidence', '—')}")
        if row["evidence"]:
            print("Evidence:")
            for item in row["evidence"]:
                snippet = " ".join(item["snippet"].split())
                if len(snippet) > 180:
                    snippet = snippet[:177] + "..."
                print(f"  - {item['path']}: {snippet}")
        else:
            print("Evidence: none in the analyzed files")
        print(f"Reason: {row['reason']}")
        print("-" * 60)


def main() -> None:
    job_text = JOB_FILE.read_text(encoding="utf-8")
    commit = get_latest_commit(REPO_URL)
    files = list_code_files(REPO_URL)

    print(f"Repo: {REPO_URL}")
    print(f"Latest commit: {commit['sha']}")
    print(f"Commit message: {commit['short_message']}")
    print(f"Files analyzed: {len(files)}")
    for file in files:
        print(f"  - {file['path']} ({file['size']} bytes)")
    print()

    print("Extracting technical requirements from job.txt...")
    requirements = extract_requirements(job_text)
    print(f"Requirements found: {len(requirements)}")
    print()

    print("Assessing the GitHub repo against those requirements...")
    assessments = assess_requirements(requirements, files)
    print()
    _print_table(assessments)


if __name__ == "__main__":
    main()
