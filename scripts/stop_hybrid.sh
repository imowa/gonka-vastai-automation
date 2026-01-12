#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
PID_DIR="${ROOT_DIR}/scripts/pids"

stop_process() {
  local name=$1
  local pid_file="${PID_DIR}/${name}.pid"

  if [[ ! -f "${pid_file}" ]]; then
    echo "No PID file for ${name}."
    return
  fi

  local pid
  pid=$(cat "${pid_file}")

  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}"
    echo "Stopped ${name} (PID ${pid})."
  else
    echo "${name} not running (stale PID ${pid})."
  fi

  rm -f "${pid_file}"
}

stop_process "poc_scheduler"
stop_process "hyperbolic_proxy"
