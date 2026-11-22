# Jenkins lab

A disposable Jenkins for exercising the OpenSRE Jenkins integration, meant for
GitHub Codespaces or the dev container. Lab only: the login is `admin` /
`admin` and a Jenkins admin can run arbitrary code, so keep the forwarded port
**private** and never expose it publicly. Outside Codespaces the port is
published on `127.0.0.1` only; set `JENKINS_LAB_BIND` to override.

## Start

```bash
.devcontainer/jenkins-lab/up.sh
```

Add `--with-plugins` to also install the Folders and Pipeline plugins and seed a
folder job and a Pipeline job. Re-running `up.sh` recreates the container from
scratch.

Open Jenkins from the **Ports** tab (port 8090). Then point OpenSRE at it:

```bash
export JENKINS_URL=http://127.0.0.1:8090 JENKINS_USER=admin JENKINS_API_TOKEN=admin
opensre integrations verify jenkins
opensre --json ask "Why did the latest build of deploy-fail fail? Put the evidence in your final answer."
```

OpenSRE needs a model. Either sign in with `opensre`, set an API key, or
install Claude Code and use it as the provider:

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude        # sign in once
export LLM_PROVIDER=claude-code
```

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

Verified against a live Jenkins for freestyle jobs only. Still open:

- `--with-plugins` and the two plugin-backed jobs have never been run; the
  environment they were written in could not reach the Jenkins update site.
- Folder, Pipeline and Multibranch behavior is unverified against a live
  server. Branch names containing `/` are stored as `feature%2Ffoo` and may 404
  because `_job_api_path` does not re-encode them.
- `get_build_log` loads the whole console log before keeping the tail
  (measured: 258 MB peak for the 86 MB `big-log`).
- `list_jobs` and `list_running_builds` fetch the full job tree in one request
  and cap at 200 jobs only afterwards.
- `list_builds` sees only the 50 newest builds and has no time-window filter.
- `JenkinsConfig` has no TLS options (custom CA, verify).

Run the focused tests with:

```bash
python -m pytest tests/integrations/test_jenkins.py tests/tools/test_jenkins_tools.py
```
