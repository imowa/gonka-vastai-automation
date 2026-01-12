#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

ENV_FILE="${ROOT_DIR}/config/.env"
VENV_ACTIVATE="${ROOT_DIR}/venv/bin/activate"
LOG_DIR="${ROOT_DIR}/logs"
PID_DIR="${ROOT_DIR}/scripts/pids"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -f "${VENV_ACTIVATE}" ]]; then
  # shellcheck disable=SC1090
  source "${VENV_ACTIVATE}"
else
  echo "Virtualenv not found at ${VENV_ACTIVATE}." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${PID_DIR}"

start_process() {
  local name=$1
  local command=$2
  local pid_file="${PID_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"

  if [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
    echo "${name} already running with PID $(cat "${pid_file}")."
    return
  fi

  nohup bash -c "${command}" >"${log_file}" 2>&1 &
  echo $! > "${pid_file}"
  echo "Started ${name} (PID $(cat "${pid_file}")). Logs: ${log_file}"
}

start_process "hyperbolic_proxy" "python3 ${ROOT_DIR}/scripts/hyperbolic_proxy.py"
start_process "poc_scheduler" "python3 ${ROOT_DIR}/scripts/3_poc_scheduler.py"
