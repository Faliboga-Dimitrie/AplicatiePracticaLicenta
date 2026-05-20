#!/usr/bin/env python3
"""
Smoke-test client for the Brain MRI Processing FastAPI backend.

This script calls the API over HTTP, the same way the future React frontend will.
It does not import the backend package directly.

Default behavior is conservative: it checks login, authorized subjects, cases,
job listing, artifact listing, and evolution-date readiness. Expensive MRI tasks
are only started when you pass --run-preprocessing and/or --run-mesh.

Examples:

  python api_smoke_test.py --email test@example.com --password secret

  python api_smoke_test.py \
      --email test@example.com \
      --password secret \
      --create-subject-if-missing \
      --new-subject-id IXI012-HH-1211-T1

  python api_smoke_test.py \
      --email test@example.com \
      --password secret \
      --subject-id IXI012-HH-1211-T1 \
      --case-id 1 \
      --run-preprocessing \
      --run-mesh \
      --run-evolution-report

Environment variable alternatives:

  MRI_API_BASE_URL=http://127.0.0.1:8000
  MRI_API_EMAIL=test@example.com
  MRI_API_PASSWORD=secret
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
SUCCESS_JOB_STATUS = "completed"


class SmokeTestError(RuntimeError):
    pass


@dataclass
class ApiError(RuntimeError):
    method: str
    url: str
    status_code: int | None
    body: str

    def __str__(self) -> str:
        status = self.status_code if self.status_code is not None else "network-error"
        return f"{self.method} {self.url} failed with {status}: {self.body}"


class ApiClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 60.0, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verbose = verbose

    def set_token(self, token: str) -> None:
        self.token = token

    def get(self, path: str, *, params: dict[str, Any] | None = None, expect_json: bool = True) -> Any:
        return self.request("GET", path, params=params, expect_json=expect_json)

    def post(self, path: str, *, json_body: Any | None = None, params: dict[str, Any] | None = None, expect_json: bool = True) -> Any:
        return self.request("POST", path, params=params, json_body=json_body, expect_json=expect_json)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        expect_json: bool = True,
    ) -> Any:
        if not path.startswith("/"):
            path = f"/{path}"

        url = f"{self.base_url}{path}"
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"

        headers = {"Accept": "application/json" if expect_json else "*/*"}
        body_bytes: bytes | None = None

        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if self.verbose:
            print(f"  -> {method} {url}")

        request = Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("content-type", "")
        except HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise ApiError(method, url, exc.code, raw_error) from exc
        except URLError as exc:
            raise ApiError(method, url, None, str(exc)) from exc

        if not expect_json:
            return raw

        if not raw:
            return None

        text = raw.decode("utf-8", errors="replace")
        if "application/json" not in content_type and self.verbose:
            print(f"  !! Response Content-Type was {content_type!r}, trying JSON anyway.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SmokeTestError(f"Expected JSON from {method} {url}, got: {text[:500]}") from exc


def encoded_segment(value: str) -> str:
    return quote(str(value), safe="")


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def print_ok(message: str) -> None:
    print(f"[OK] {message}")


def print_warn(message: str) -> None:
    print(f"[WARN] {message}")


def create_subject_for_current_user(
    client: ApiClient,
    *,
    subject_id: str,
    name: str | None = None,
    age: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"subject_id": subject_id}
    if name is not None:
        payload["name"] = name
    if age is not None:
        payload["age"] = age
    if notes is not None:
        payload["notes"] = notes
    return client.post("/subjects", json_body=payload)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestError(message)


def pick_subject(subjects: list[dict[str, Any]], requested_subject_id: str | None) -> dict[str, Any]:
    require(subjects, "No authorized subjects returned. Create subject access before running this smoke test.")

    if requested_subject_id is None:
        return subjects[0]

    for subject in subjects:
        if subject.get("id") == requested_subject_id:
            return subject

    available = ", ".join(str(s.get("id")) for s in subjects[:10])
    raise SmokeTestError(
        f"Requested subject {requested_subject_id!r} was not visible to this user. "
        f"First visible subjects: {available}"
    )


def pick_case(cases: list[dict[str, Any]], requested_case_id: int | None) -> dict[str, Any]:
    require(cases, "No MRI cases returned for selected subject. Create/register a case first.")

    if requested_case_id is None:
        return cases[0]

    for case in cases:
        if int(case.get("id")) == requested_case_id:
            return case

    available = ", ".join(str(c.get("id")) for c in cases[:10])
    raise SmokeTestError(
        f"Requested case id {requested_case_id!r} was not returned for this subject. "
        f"First visible case ids: {available}"
    )


def summarize_artifacts(artifacts_response: dict[str, Any]) -> str:
    artifacts = artifacts_response.get("artifacts") or []
    by_kind: dict[str, int] = {}
    for artifact in artifacts:
        kind = str(artifact.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    if not by_kind:
        return "0 artifacts"
    return ", ".join(f"{kind}={count}" for kind, count in sorted(by_kind.items()))


def poll_job(client: ApiClient, job_id: str, *, poll_interval: float, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_printed: tuple[str | None, str | None, float | None] | None = None

    while True:
        job = client.get(f"/jobs/{encoded_segment(job_id)}")
        status = job.get("status")
        message = job.get("message")
        progress = job.get("progress")

        current_printed = (status, message, progress)
        if current_printed != last_printed:
            progress_text = "" if progress is None else f" progress={progress}"
            message_text = "" if not message else f" message={message!r}"
            print(f"[JOB] {job_id}: status={status}{progress_text}{message_text}")
            last_printed = current_printed

        if status in TERMINAL_JOB_STATUSES:
            if status != SUCCESS_JOB_STATUS:
                error = job.get("error") or job.get("message") or "unknown job error"
                raise SmokeTestError(f"Job {job_id} ended with status={status}: {error}")
            return job

        if time.monotonic() >= deadline:
            raise SmokeTestError(f"Timed out waiting for job {job_id} after {timeout_seconds:.0f}s.")

        time.sleep(poll_interval)


def choose_evolution_interval(
    dates_response: dict[str, Any],
    *,
    start_date: str | None,
    end_date: str | None,
    require_json_ready: bool,
    require_visual_ready: bool,
) -> tuple[str, str]:
    dates = dates_response.get("dates") or []

    if require_json_ready:
        dates = [entry for entry in dates if entry.get("ready_for_json")]
    if require_visual_ready:
        dates = [entry for entry in dates if entry.get("ready_for_visual")]

    dates = sorted(dates, key=lambda entry: entry.get("acquisition_date") or "")

    if start_date and end_date:
        return start_date, end_date

    require(len(dates) >= 2, "Need at least two evolution-ready MRI dates to build an interval.")
    return start_date or dates[0]["acquisition_date"], end_date or dates[-1]["acquisition_date"]


def download_first_artifact(client: ApiClient, artifacts_response: dict[str, Any], output_dir: Path) -> Path | None:
    artifacts = artifacts_response.get("artifacts") or []
    if not artifacts:
        return None

    preferred = None
    for artifact in artifacts:
        name = str(artifact.get("name") or "")
        if name.lower().endswith(".glb") or artifact.get("kind") in {"mesh", "wireframe"}:
            preferred = artifact
            break
    if preferred is None:
        preferred = artifacts[0]

    url = preferred.get("url")
    name = preferred.get("name") or "artifact.bin"
    require(isinstance(url, str) and url.startswith("/"), f"Artifact has no frontend-safe relative URL: {preferred}")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / str(name).replace("/", "_").replace("\\", "_")
    data = client.get(url, expect_json=False)
    out_path.write_bytes(data)
    return out_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test the Brain MRI Processing FastAPI backend.")

    parser.add_argument("--base-url", default=os.getenv("MRI_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.getenv("MRI_API_EMAIL"), help="Login email. Can also use MRI_API_EMAIL.")
    parser.add_argument("--password", default=os.getenv("MRI_API_PASSWORD"), help="Login password. Can also use MRI_API_PASSWORD.")

    parser.add_argument("--subject-id", default=None, help="Specific subject id to test. Defaults to first authorized subject.")
    parser.add_argument("--case-id", type=int, default=None, help="Specific case id to test. Defaults to first case for selected subject.")

    parser.add_argument("--create-subject-if-missing", action="store_true", help="Create a subject through POST /subjects if no authorized subjects are visible, or if --subject-id is not visible.")
    parser.add_argument("--new-subject-id", default=None, help="Subject id to create when --create-subject-if-missing is used. Defaults to --subject-id.")
    parser.add_argument("--new-subject-name", default=None, help="Optional name for the subject created by the smoke test.")
    parser.add_argument("--new-subject-age", type=int, default=None, help="Optional age for the subject created by the smoke test.")
    parser.add_argument("--new-subject-notes", default="Created by API smoke test.", help="Optional notes for the subject created by the smoke test.")

    parser.add_argument("--run-preprocessing", action="store_true", help="Actually start a preprocessing job and wait for completion.")
    parser.add_argument("--run-mesh", action="store_true", help="Actually start a mesh-analysis job and wait for completion.")

    parser.add_argument("--run-evolution-report", action="store_true", help="Call the evolution JSON endpoint.")
    parser.add_argument("--download-evolution-visual", action="store_true", help="Call the evolution visual GLB endpoint and save the volatile GLB response.")
    parser.add_argument("--start-date", default=None, help="Evolution interval start date, YYYY-MM-DD. Defaults to first ready date.")
    parser.add_argument("--end-date", default=None, help="Evolution interval end date, YYYY-MM-DD. Defaults to last ready date.")
    parser.add_argument("--target-date", default=None, help="Optional target date for visual overlay, YYYY-MM-DD.")
    parser.add_argument("--tissue", dest="tissues", action="append", choices=["gm", "wm", "csf"], help="Repeatable visual tissue filter, e.g. --tissue gm --tissue wm.")
    parser.add_argument("--no-wireframes", action="store_true", help="Do not include wireframes in the visual evolution GLB.")

    parser.add_argument("--download-first-artifact", action="store_true", help="Download one served artifact file to verify artifact file responses.")
    parser.add_argument("--require-artifacts", action="store_true", help="Fail if the selected case has no artifacts.")
    parser.add_argument("--output-dir", type=Path, default=Path("smoke_test_outputs"))

    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--job-timeout", type=float, default=60 * 60, help="Seconds to wait for each long-running job.")
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--verbose", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.email or not args.password:
        print("Missing credentials. Pass --email/--password or set MRI_API_EMAIL/MRI_API_PASSWORD.", file=sys.stderr)
        return 2

    client = ApiClient(args.base_url, timeout=args.request_timeout, verbose=args.verbose)

    try:
        print_header("1. Login")
        login_response = client.post("/auth/login", json_body={"email": args.email, "password": args.password})
        token = login_response.get("access_token")
        require(isinstance(token, str) and token, "Login response did not contain access_token.")
        client.set_token(token)
        user = login_response.get("user") or {}
        print_ok(f"Logged in as user_id={user.get('id')} email={user.get('email')}")

        print_header("2. Current user")
        me_response = client.get("/auth/me")
        print_ok(f"/auth/me returned {me_response.get('user')}")

        print_header("3. Authorized subjects")
        subjects = client.get("/subjects")
        require(isinstance(subjects, list), "/subjects did not return a list.")

        try:
            selected_subject = pick_subject(subjects, args.subject_id)
        except SmokeTestError as exc:
            if not args.create_subject_if_missing:
                raise

            new_subject_id = args.new_subject_id or args.subject_id
            require(
                isinstance(new_subject_id, str) and new_subject_id.strip(),
                "--create-subject-if-missing requires --new-subject-id or --subject-id.",
            )

            print_warn(f"{exc} Creating subject {new_subject_id!r} for the current user.")
            created_subject = create_subject_for_current_user(
                client,
                subject_id=new_subject_id,
                name=args.new_subject_name,
                age=args.new_subject_age,
                notes=args.new_subject_notes,
            )
            print_ok(
                f"Created subject {created_subject.get('id')!r} "
                f"with role={created_subject.get('role')!r}."
            )

            subjects = client.get("/subjects")
            require(isinstance(subjects, list), "/subjects did not return a list after subject creation.")
            selected_subject = pick_subject(subjects, new_subject_id)

        subject_id = str(selected_subject["id"])
        print_ok(f"Loaded {len(subjects)} authorized subject(s); selected {subject_id!r}.")

        print_header("4. Subject cases")
        cases = client.get(f"/subjects/{encoded_segment(subject_id)}/cases")
        require(isinstance(cases, list), f"/subjects/{subject_id}/cases did not return a list.")
        selected_case = pick_case(cases, args.case_id)
        case_id = int(selected_case["id"])
        acquisition_date = selected_case.get("acquisition_date")
        print_ok(f"Loaded {len(cases)} case(s); selected case_id={case_id}, acquisition_date={acquisition_date}.")

        print_header("5. Case details")
        case_response = client.get(f"/cases/{case_id}")
        print_ok(f"Case status={case_response.get('status')}, case_key={case_response.get('case_key')}")

        print_header("6. Existing jobs")
        jobs_response = client.get("/jobs", params={"case_id": case_id})
        require(isinstance(jobs_response, list), "/jobs did not return a list.")
        print_ok(f"Loaded {len(jobs_response)} existing job(s) for case_id={case_id}.")

        if args.run_preprocessing:
            print_header("7. Start preprocessing job")
            preprocessing_job = client.post(f"/processing/cases/{case_id}/preprocessing-jobs")
            preprocessing_job_id = preprocessing_job.get("id")
            require(isinstance(preprocessing_job_id, str) and preprocessing_job_id, "Preprocessing job response has no id.")
            print_ok(f"Started preprocessing job {preprocessing_job_id}.")
            preprocessing_job = poll_job(
                client,
                preprocessing_job_id,
                poll_interval=args.poll_interval,
                timeout_seconds=args.job_timeout,
            )
            print_ok(f"Preprocessing job completed: {preprocessing_job.get('message')}")
        else:
            print_header("7. Preprocessing job")
            print_warn("Skipped because --run-preprocessing was not provided.")

        if args.run_mesh:
            print_header("8. Start mesh-analysis job")
            mesh_job = client.post(f"/processing/cases/{case_id}/mesh-analysis-jobs")
            mesh_job_id = mesh_job.get("id")
            require(isinstance(mesh_job_id, str) and mesh_job_id, "Mesh-analysis job response has no id.")
            print_ok(f"Started mesh-analysis job {mesh_job_id}.")
            mesh_job = poll_job(
                client,
                mesh_job_id,
                poll_interval=args.poll_interval,
                timeout_seconds=args.job_timeout,
            )
            result = mesh_job.get("result") or {}
            print_ok(f"Mesh-analysis job completed. artifacts_url={result.get('artifacts_url')}")
        else:
            print_header("8. Mesh-analysis job")
            print_warn("Skipped because --run-mesh was not provided.")

        print_header("9. Artifacts")
        artifacts_response: dict[str, Any] | None = None
        try:
            artifacts_response = client.get(f"/cases/{case_id}/artifacts")
            print_ok(f"Artifact listing returned {summarize_artifacts(artifacts_response)}.")
            if args.require_artifacts:
                require(bool(artifacts_response.get("artifacts")), "Artifact list is empty but --require-artifacts was provided.")
            if args.download_first_artifact:
                out_path = download_first_artifact(client, artifacts_response, args.output_dir)
                if out_path is None:
                    require(not args.require_artifacts, "No artifact available to download.")
                    print_warn("No artifacts available to download.")
                else:
                    print_ok(f"Downloaded artifact to {out_path} ({out_path.stat().st_size} bytes).")
        except ApiError as exc:
            if args.require_artifacts:
                raise
            print_warn(f"Artifact listing failed, but artifacts are optional in this run: {exc}")

        print_header("10. Evolution dates")
        evolution_dates = client.get(f"/processing/subjects/{encoded_segment(subject_id)}/evolution/dates")
        date_entries = evolution_dates.get("dates") or []
        ready_json = [entry for entry in date_entries if entry.get("ready_for_json")]
        ready_visual = [entry for entry in date_entries if entry.get("ready_for_visual")]
        print_ok(
            f"Evolution date endpoint returned {len(date_entries)} date(s); "
            f"json-ready={len(ready_json)}, visual-ready={len(ready_visual)}."
        )

        if args.run_evolution_report:
            print_header("11. Evolution JSON report")
            start_date, end_date = choose_evolution_interval(
                evolution_dates,
                start_date=args.start_date,
                end_date=args.end_date,
                require_json_ready=True,
                require_visual_ready=False,
            )
            report = client.get(
                f"/processing/subjects/{encoded_segment(subject_id)}/evolution",
                params={"start_date": start_date, "end_date": end_date},
            )
            points = report.get("points") or []
            statistics = report.get("statistics") or {}
            print_ok(
                f"Evolution report built for {start_date} -> {end_date}; "
                f"points={len(points)}, statistic groups={len(statistics)}."
            )
        else:
            print_header("11. Evolution JSON report")
            print_warn("Skipped because --run-evolution-report was not provided.")

        if args.download_evolution_visual:
            print_header("12. Evolution visual GLB")
            start_date, end_date = choose_evolution_interval(
                evolution_dates,
                start_date=args.start_date,
                end_date=args.end_date,
                require_json_ready=False,
                require_visual_ready=True,
            )
            params: dict[str, Any] = {
                "start_date": start_date,
                "end_date": end_date,
                "include_wireframes": "false" if args.no_wireframes else "true",
            }
            if args.target_date:
                params["target_date"] = args.target_date
            if args.tissues:
                params["tissues"] = args.tissues

            glb_bytes = client.get(
                f"/processing/subjects/{encoded_segment(subject_id)}/evolution/visual",
                params=params,
                expect_json=False,
            )
            require(glb_bytes.startswith(b"glTF"), "Evolution visual response does not look like a binary GLB file.")
            args.output_dir.mkdir(parents=True, exist_ok=True)
            target = args.target_date or end_date
            out_path = args.output_dir / f"{subject_id}_{start_date}_to_{target}_comparison.glb"
            out_path.write_bytes(glb_bytes)
            print_ok(f"Downloaded volatile comparison GLB to {out_path} ({out_path.stat().st_size} bytes).")
        else:
            print_header("12. Evolution visual GLB")
            print_warn("Skipped because --download-evolution-visual was not provided.")

        print_header("Result")
        print_ok("Smoke test completed successfully.")
        return 0

    except (ApiError, SmokeTestError) as exc:
        print_header("Result")
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
