#!/usr/bin/env bash
# Start a disposable Jenkins with seeded jobs for exercising the OpenSRE
# Jenkins integration. Usage: up.sh [--with-plugins]
set -euo pipefail

readonly LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONTAINER="jenkins-dev"
readonly IMAGE="jenkins/jenkins:lts-jdk21"
readonly PORT="${JENKINS_LAB_PORT:-8090}"
# Jenkins admin can run arbitrary code, so publish on loopback only. Codespaces
# is the exception: its port forwarder needs the port on the VM's interfaces,
# and the VM is reachable only through forwarded ports, which default to private.
if [[ "${CODESPACES:-}" == "true" ]]; then
  readonly DEFAULT_BIND_ADDRESS="0.0.0.0"
else
  readonly DEFAULT_BIND_ADDRESS="127.0.0.1"
fi
readonly BIND_ADDRESS="${JENKINS_LAB_BIND:-${DEFAULT_BIND_ADDRESS}}"
readonly URL="http://127.0.0.1:${PORT}"
readonly AUTH="admin:admin"
readonly COOKIES="$(mktemp)"
readonly READY_ATTEMPTS=90
readonly PLUGINS=(cloudbees-folder workflow-aggregator pipeline-stage-view)
trap 'rm -f "${COOKIES}"' EXIT

anonymous_curl() {
  curl --silent --show-error --noproxy '*' "$@"
}

jenkins_curl() {
  anonymous_curl --user "${AUTH}" "$@"
}

# wait_until_ready <curl-function>: poll with the given credentials mode.
wait_until_ready() {
  local curl_fn="$1" attempt
  for ((attempt = 1; attempt <= READY_ATTEMPTS; attempt++)); do
    if "${curl_fn}" --fail --output /dev/null "${URL}/api/json" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Jenkins did not become ready at ${URL}" >&2
  docker logs --tail 20 "${CONTAINER}" >&2
  return 1
}

start_jenkins() {
  docker rm --force "${CONTAINER}" >/dev/null 2>&1 || true
  docker create --name "${CONTAINER}" --publish "${BIND_ADDRESS}:${PORT}:8080" \
    --env JAVA_OPTS="-Djenkins.install.runSetupWizard=false" "${IMAGE}" >/dev/null
  docker start "${CONTAINER}" >/dev/null
  wait_until_ready anonymous_curl
}

# Jenkins boots with security off, so the script console accepts the setup
# script anonymously. Sent over HTTP from stdin instead of copied or mounted
# into the container: no host path reaches Docker, which keeps this working
# with docker-outside-of-docker and with Git Bash path conversion on Windows.
enable_security() {
  local bootstrap_crumb
  bootstrap_crumb="$(crumb anonymous_curl)"
  anonymous_curl --fail --output /dev/null --cookie "${COOKIES}" \
    --header "Jenkins-Crumb: ${bootstrap_crumb}" \
    --data-urlencode "script@-" "${URL}/scriptText" <"${LAB_DIR}/basic-security.groovy"
  wait_until_ready jenkins_curl
}

install_plugins() {
  docker exec "${CONTAINER}" jenkins-plugin-cli --plugins "${PLUGINS[@]}"
  docker restart "${CONTAINER}" >/dev/null
  wait_until_ready jenkins_curl
}

# crumb <curl-function>: print a CSRF crumb and keep its session cookie.
crumb() {
  local curl_fn="$1"
  "${curl_fn}" --cookie-jar "${COOKIES}" "${URL}/crumbIssuer/api/json" |
    sed -n 's/.*"crumb":"\([^"]*\)".*/\1/p'
}

# create_item <parent-path> <name> <config-xml>, e.g. create_item "" deploy-ok "<project/>"
create_item() {
  local parent="$1" name="$2" config="$3"
  jenkins_curl --fail --output /dev/null --cookie "${COOKIES}" \
    --header "Jenkins-Crumb: ${CRUMB}" --header "Content-Type: application/xml" \
    --data-binary "${config}" "${URL}${parent}/createItem?name=${name}"
}

trigger_build() {
  local job_path="$1"
  jenkins_curl --fail --output /dev/null --cookie "${COOKIES}" \
    --header "Jenkins-Crumb: ${CRUMB}" --request POST "${URL}${job_path}/build"
}

freestyle_config() {
  local command="$1" shell_options="${2:-}"
  printf '<project><builders><hudson.tasks.Shell><command>%s</command>%s</hudson.tasks.Shell></builders></project>' \
    "${command}" "${shell_options}"
}

seed_freestyle_job() {
  local name="$1" command="$2" shell_options="${3:-}"
  create_item "" "${name}" "$(freestyle_config "${command}" "${shell_options}")"
  trigger_build "/job/${name}"
  echo "seeded ${name}"
}

seed_freestyle_jobs() {
  seed_freestyle_job deploy-ok 'echo ok'
  seed_freestyle_job deploy-fail 'echo deploying payment-service; exit 1'
  seed_freestyle_job tests-unstable 'echo 3 tests failed; exit 2' '<unstableReturn>2</unstableReturn>'
  seed_freestyle_job big-log \
    'yes line-of-log-output-padding-padding-padding | head -n 2000000; echo THE-REAL-ERROR; exit 1'
}

seed_plugin_jobs() {
  local pipeline_script
  pipeline_script="node { stage('Build') { echo 'build ok' }; stage('Deploy') { error 'deploy step failed' } }"
  create_item "" team '<com.cloudbees.hudson.plugins.folder.Folder/>'
  create_item "/job/team" payment-service "$(freestyle_config 'echo folder job; exit 1')"
  trigger_build "/job/team/job/payment-service"
  create_item "" release-pipeline \
    "<flow-definition><definition class=\"org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition\"><script>${pipeline_script}</script><sandbox>true</sandbox></definition></flow-definition>"
  trigger_build "/job/release-pipeline"
  echo "seeded team/payment-service and release-pipeline"
}

main() {
  local with_plugins="false"
  [[ "${1:-}" == "--with-plugins" ]] && with_plugins="true"

  start_jenkins
  enable_security
  [[ "${with_plugins}" == "true" ]] && install_plugins
  CRUMB="$(crumb jenkins_curl)"
  seed_freestyle_jobs
  [[ "${with_plugins}" == "true" ]] && seed_plugin_jobs

  cat <<SUMMARY

Jenkins is up at ${URL} (login: admin / admin)
Point OpenSRE at it:
  export JENKINS_URL=${URL} JENKINS_USER=admin JENKINS_API_TOKEN=admin
  opensre integrations verify jenkins
SUMMARY
}

main "$@"
