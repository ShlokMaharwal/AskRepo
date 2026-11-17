"""Validate a deployment using public API calls; never creates or deletes repositories."""

import argparse
import json
import sys
import time
from urllib.parse import urlsplit

import httpx

DEMOS = {"Seekr", "CodeNest", "DPTrace"}


class SmokeFailure(Exception):
    pass


def origin(value):
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise SmokeFailure(
            "Supply an HTTP(S) base origin without credentials, paths or queries"
        )
    return f"{url.scheme}://{url.netloc}"


def checked(response, label):
    if response.status_code != 200:
        raise SmokeFailure(f"{label}: HTTP {response.status_code}")
    return response


def stream_answer(lines):
    name, data = "", []
    events, answer, citations, terminal = [], "", [], None
    for line in lines:
        if line.startswith(":"):
            continue
        if line:
            field, _, value = line.partition(":")
            if field == "event":
                name = value.lstrip(" ")
            elif field == "data":
                data.append(value.lstrip(" "))
            continue
        if not data:
            continue
        payload = json.loads("\n".join(data))
        events.append(name)
        if name == "error":
            raise SmokeFailure("Stream returned a terminal application error")
        if name == "token":
            answer += payload["text"]
        elif name == "answer_clean":
            answer = payload["answer"]
        elif name == "citations":
            citations = payload
        elif name == "done":
            terminal = payload
        name, data = "", []
    if data or not {"status", "chunks", "token", "done"} <= set(events):
        raise SmokeFailure("Stream was truncated or is missing required events")
    if terminal is None or terminal.get("notFound") or not answer.strip():
        raise SmokeFailure("Stream did not produce a completed repository answer")
    if events.index("chunks") > events.index("token") or events[-1] != "done":
        raise SmokeFailure("Stream event order is invalid")
    return citations


def validate_citations(client, api, repo_id, citations):
    if not citations:
        raise SmokeFailure("Answer has no validated citations")
    files = {}
    for cite in citations:
        path = cite["path"]
        if path not in files:
            file = checked(
                client.get(api + "/file", params={"repoId": repo_id, "path": path}),
                "Cited source file",
            ).json()
            files[path] = file["content"].splitlines()
        if not 1 <= cite["startLine"] <= cite["endLine"] <= len(files[path]):
            raise SmokeFailure("Citation range is outside the source file")


def smoke(api, frontend, client, *, wait_seconds=0, delay_seconds=20, sleep=time.sleep):
    api, frontend = origin(api), origin(frontend)
    checked(client.get(frontend), "Frontend")
    print("PASS frontend responds", flush=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            response = client.get(api + "/health")
            health = response.json() if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            health = {}
        demos = health.get("demoRepos", [])
        if health.get("status") == "ok" and DEMOS <= {
            row["name"] for row in demos if row["status"] == "ready"
        }:
            break
        if time.monotonic() >= deadline:
            raise SmokeFailure(
                "Demos are not all ready; enable bootstrap and wait for indexing"
            )
        sleep(min(10, max(0, deadline - time.monotonic())))
    print("PASS health and all three demo readiness states", flush=True)
    cors = checked(
        client.options(
            api + "/ask/stream",
            headers={
                "Origin": frontend,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        ),
        "CORS preflight",
    )
    if cors.headers.get("access-control-allow-origin") != frontend:
        raise SmokeFailure("CORS does not allow the exact frontend origin")
    print("PASS stream CORS preflight", flush=True)
    repos = checked(client.get(api + "/repos"), "Repository list").json()
    by_name = {repo["repoUrl"].rstrip("/").rsplit("/", 1)[-1]: repo for repo in repos}
    if not DEMOS <= by_name.keys():
        raise SmokeFailure("/repos is missing ready demo repositories")
    print("PASS /repos contains the three ready demos", flush=True)
    repo_id = by_name["Seekr"]["repoId"]
    body = {
        "repoId": repo_id,
        "question": "How does the Redis URL frontier queue work?",
        "topK": 5,
        "hybrid": True,
        "rerank": False,
        "agentic": False,
    }
    answer = checked(client.post(api + "/ask", json=body), "JSON answer").json()
    if answer.get("notFound") or not answer.get("answer", "").strip():
        raise SmokeFailure("JSON answer did not find repository evidence")
    validate_citations(client, api, repo_id, answer.get("citations", []))
    print("PASS /ask returns citations within real source-file bounds", flush=True)
    sleep(delay_seconds)
    body["question"] = "Which files implement the Redis URL frontier queue?"
    with client.stream("POST", api + "/ask/stream", json=body) as response:
        checked(response, "SSE answer")
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise SmokeFailure("Streaming response has the wrong content type")
        citations = stream_answer(response.iter_lines())
    validate_citations(client, api, repo_id, citations)
    print(
        "PASS /ask/stream yields status, chunks, token and done with valid citations",
        flush=True,
    )
    print(
        "PASS deployment smoke checks (structural validity, not semantic faithfulness)",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("api_url")
    parser.add_argument("frontend_url")
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--delay-seconds", type=float, default=20)
    args = parser.parse_args()
    if args.wait_seconds < 0 or args.delay_seconds < 0:
        parser.error("Wait and delay must be nonnegative")
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            smoke(
                args.api_url,
                args.frontend_url,
                client,
                wait_seconds=args.wait_seconds,
                delay_seconds=args.delay_seconds,
            )
    except (SmokeFailure, httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        message = (
            str(error) if isinstance(error, SmokeFailure) else type(error).__name__
        )
        print("FAIL " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
