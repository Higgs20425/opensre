# Jenkins lab

A disposable Jenkins for exercising the OpenSRE Jenkins integration, on a local
machine with Docker or in GitHub Codespaces. Lab only: the login is `admin` /
`admin` and a Jenkins admin can run arbitrary code, so never expose the port
publicly. Outside Codespaces it is published on `127.0.0.1` only; set
`JENKINS_LAB_BIND` to override. In Codespaces keep the forwarded port
**private**.

## Start

Needs Docker running (Docker Desktop on Windows and macOS) plus `bash` and
`curl`. On Windows run it from Git Bash or WSL.

```bash
.devcontainer/jenkins-lab/up.sh
```

Add `--with-plugins` to also install the Folders and Pipeline plugins and seed a
folder job and a Pipeline job. Re-running `up.sh` recreates the container from
scratch; `--seed-only` configures a Jenkins started by Compose instead (see
below). Jenkins starts unsecured for a few seconds until the script enables
the login.

Open http://localhost:8090 in a browser (in Codespaces, use the **Ports** tab).

## Run OpenSRE in a container

To keep OpenSRE off the host, start both services with Compose and configure
the freshly started Jenkins:

```bash
docker compose -f .devcontainer/jenkins-lab/compose.yaml up -d --build
.devcontainer/jenkins-lab/up.sh --seed-only
docker compose -f .devcontainer/jenkins-lab/compose.yaml exec opensre bash
```

The `opensre` container runs this checkout's code with no host mounts and no
published ports. It reaches Jenkins at `http://jenkins:8080` over the lab
network, and the lab login is preset in its environment, so
`opensre integrations verify jenkins` works as soon as Jenkins is seeded.

- Model: run `claude`, sign in with `/login`, then
  `export LLM_PROVIDER=claude-code`. To leave the Claude Code CLI out, run
  `docker compose -f .devcontainer/jenkins-lab/compose.yaml build --build-arg INSTALL_CLAUDE_CODE=false`
  before `up`.
- Anything entered inside the container (model sign-in,
  `opensre integrations setup ...`) stays there. `stop` and `start` keep it;
  `down` deletes it with the container.
- After saving any integration with `opensre integrations setup`, also run
  `opensre integrations setup jenkins` (`http://jenkins:8080`, `admin`,
  `admin`). `opensre ask` ignores integrations from environment variables once
  the local store has an entry, while `integrations verify` still passes.
- `--seed-only` expects a Jenkins that has just started. To reseed, run `down`,
  then the commands above again. `--with-plugins` can be combined with it.

## Run OpenSRE against it from the host

From the repository root, install once with `make install`, then:

```bash
export JENKINS_URL=http://127.0.0.1:8090 JENKINS_USER=admin JENKINS_API_TOKEN=admin
uv run opensre integrations verify jenkins
uv run opensre --json ask "Why did the latest build of deploy-fail fail? Put the evidence in your final answer."
```

Without `--json`, `ask` prints only the closing summary of a multi-step
investigation.

OpenSRE needs a model. Sign in with `uv run opensre`, set an API key, or use an
installed and signed-in Claude Code CLI with `export LLM_PROVIDER=claude-code`.
Never commit a key: this repository is public.

## Repository layout for this work

- `origin` is the fork `Higgs20425/opensre`; upstream is `tracer-cloud/opensre`.
- `jenkins-reliability-fixes` holds only the integration fixes, kept clean for
  an upstream pull request. `jenkins-lab` adds this lab on top of it.
- Put integration changes on `jenkins-reliability-fixes` and lab changes on
  `jenkins-lab`. Do not put session URLs in commit messages.

## Seeded jobs

| Job | Result | Exercises |
| --- | --- | --- |
| `deploy-ok` | SUCCESS | Healthy baseline |
| `deploy-fail` | FAILURE | Root cause in the console log tail |
| `tests-unstable` | UNSTABLE | Unstable builds cited beside failures |
| `big-log` | FAILURE | 86 MB console log |
| `team/payment-service` (`--with-plugins`) | FAILURE | Folder job paths |
| `release-pipeline` (`--with-plugins`) | FAILURE | Pipeline stages; `Deploy` stage fails |

## Status of the integration work

Branch `jenkins-reliability-fixes` (this branch builds on it) fixed, with unit
tests in `tests/integrations/test_jenkins.py` and
`tests/tools/test_jenkins_tools.py`:

- `get_pipeline_stages` reports a missing job or build as an error instead of
  "not a pipeline".
- UNSTABLE builds and jobs are returned and cited in evidence summaries.
- Connection drops and HTTP 502/503/504 are retried; timeouts are not.

Verified against a live Jenkins for freestyle, folder and Pipeline jobs,
including `--with-plugins` and both plugin-backed jobs. Still open:

- `up.sh` and `compose.yaml` have been run on Linux and on Git Bash with Docker
  Desktop for Windows. WSL and Codespaces are untested.
- Multibranch behavior is unverified against a live server. Branch names
  containing `/` are stored as `feature%2Ffoo` and may 404 because
  `_job_api_path` does not re-encode them.
- `get_build_log` loads the whole console log before keeping the tail
  (measured: 258 MB peak for the 86 MB `big-log`).
- `list_jobs` and `list_running_builds` fetch the full job tree in one request
  and cap at 200 jobs only afterwards.
- `list_builds` sees only the 50 newest builds and has no time-window filter.
- `JenkinsConfig` has no TLS options (custom CA, verify).

Run the focused tests with:

```bash
uv run python -m pytest tests/integrations/test_jenkins.py tests/tools/test_jenkins_tools.py
```
