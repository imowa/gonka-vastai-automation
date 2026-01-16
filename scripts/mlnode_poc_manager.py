#!/usr/bin/env python3
"""
Official MLNode PoC Manager
Integrates with the official MLNode Docker container for PoC computation.
Uses the full MLNode API instead of raw vLLM.
"""

import os
import time
import json
import logging
import requests
import paramiko
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MLNodePoCManager:
    """
    Manages MLNode instances on Vast.ai for PoC computation.
    Uses the official MLNode Docker image with full PoC support.
    """

    def __init__(self):
        self.admin_api_url = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')
        self.ssh_key_path = os.path.expanduser(os.getenv('VASTAI_SSH_KEY_PATH', '~/.ssh/id_rsa'))

        # MLNode configuration
        self.poc_model = os.getenv('MLNODE_POC_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        self.mlnode_port = int(os.getenv('MLNODE_PORT', '5070'))
        self.mlnode_api_segment = os.getenv('MLNODE_API_SEGMENT', '/api/v1')
        self.mlnode_inference_segment = os.getenv('MLNODE_INFERENCE_SEGMENT', '/v1')

        # Hardware settings
        self.hardware_type = os.getenv('VASTAI_GPU_TYPE', 'RTX_4090')
        self.hardware_count = int(os.getenv('VASTAI_NUM_GPUS', '1'))

        # Timeouts
        self.ssh_ready_timeout = int(os.getenv('VASTAI_SSH_READY_TIMEOUT', '900'))
        self.mlnode_startup_timeout = int(os.getenv('MLNODE_STARTUP_TIMEOUT', '1800'))
        self.poc_execution_timeout = int(os.getenv('POC_EXECUTION_TIMEOUT', '900'))

        logger.info("MLNode PoC Manager initialized")
        logger.info("PoC model: %s", self.poc_model)
        logger.info("MLNode port: %s", self.mlnode_port)
        logger.info("MLNode startup timeout: %ss (%s minutes)",
                   self.mlnode_startup_timeout, self.mlnode_startup_timeout // 60)

    def get_ssh_connection(self, vastai_manager, instance_id: int) -> Optional[Dict]:
        """Get connection details from Vast.ai instance"""
        try:
            time.sleep(1)  # Rate limiting

            response = vastai_manager.get_instance_status(instance_id)
            if not response:
                logger.error("No response from Vast.ai API")
                return None

            status = response.get('instances', {})
            if not status:
                logger.error("No instances data in response")
                return None

            ssh_host = status.get('ssh_host')
            ssh_port = status.get('ssh_port', 22)

            # DEBUG: Log ALL fields to find the port mapping
            all_fields = list(status.keys())
            logger.info(f"DEBUG - Total fields: {len(all_fields)}")
            logger.info(f"DEBUG - ALL status fields: {all_fields}")

            # Check extra_env for port mapping (VAST_TCP_PORT_5070=10087)
            extra_env = status.get('extra_env', {})
            logger.info(f"DEBUG - extra_env: {extra_env}")

            # Look for any field containing "5070" or the mlnode port
            matching_fields = {}
            for k, v in status.items():
                if isinstance(v, (str, int)) and ('5070' in str(k) or '5070' in str(v)):
                    matching_fields[k] = v
            logger.info(f"DEBUG - Fields containing '5070': {matching_fields}")

            # Try to get port from extra_env (VAST_TCP_PORT_5070)
            mlnode_port_from_env = None
            if isinstance(extra_env, dict):
                mlnode_port_from_env = extra_env.get(f'VAST_TCP_PORT_{self.mlnode_port}')

            logger.info(f"DEBUG - VAST_TCP_PORT_{self.mlnode_port} from env: {mlnode_port_from_env}")

            # Get the externally mapped MLNode port (Vast.ai maps internal ports to external ones)
            mlnode_port = (
                mlnode_port_from_env or  # Try environment variable first
                status.get(f'direct_port_{self.mlnode_port}') or
                status.get('direct_port_5070') or
                status.get(f'ports.{self.mlnode_port}/tcp') or
                status.get('port_mappings', {}).get(str(self.mlnode_port)) or
                status.get('ports', {}).get(f'{self.mlnode_port}/tcp') or
                self.mlnode_port  # Fallback to default
            )

            if not ssh_host:
                logger.error("SSH host not found in response")
                return None

            logger.info(f"Instance ports - SSH: {ssh_port}, MLNode API: {mlnode_port} (internal: {self.mlnode_port})")

            return {
                'host': ssh_host,
                'port': int(ssh_port),
                'username': 'root',
                'mlnode_port': int(mlnode_port)
            }
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            return None

    def wait_for_ssh_ready(self, ssh_info: Dict, max_wait: int = 900) -> bool:
        """Wait for SSH to be ready on the remote instance"""
        logger.info(f"Waiting for SSH to be ready at {ssh_info['host']}:{ssh_info['port']}...")

        start_time = time.time()
        attempt = 0

        while (time.time() - start_time) < max_wait:
            attempt += 1
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_path)

                ssh.connect(
                    hostname=ssh_info['host'],
                    port=ssh_info['port'],
                    username=ssh_info['username'],
                    pkey=private_key,
                    timeout=10,
                    banner_timeout=30
                )

                stdin, stdout, stderr = ssh.exec_command("echo 'SSH test'", timeout=5)
                exit_code = stdout.channel.recv_exit_status()

                ssh.close()

                if exit_code == 0:
                    logger.info(f"✅ SSH is ready (attempt #{attempt})")
                    return True

            except paramiko.ssh_exception.AuthenticationException:
                if attempt % 6 == 0:
                    elapsed = int(time.time() - start_time)
                    logger.info(f"SSH auth not ready yet ({elapsed}s elapsed)... Retrying")
                time.sleep(5)

            except Exception as e:
                if attempt % 6 == 0:
                    elapsed = int(time.time() - start_time)
                    logger.info(f"SSH not ready yet ({elapsed}s elapsed)... Retrying")
                time.sleep(5)

        elapsed = int(time.time() - start_time)
        logger.error(f"SSH failed to be ready after {elapsed}s")
        return False

    def ssh_execute(self, ssh_info: Dict, command: str, timeout: int = 300) -> tuple:
        """Execute command via SSH"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_path)

            ssh.connect(
                hostname=ssh_info['host'],
                port=ssh_info['port'],
                username=ssh_info['username'],
                pkey=private_key,
                timeout=15,
                banner_timeout=30
            )

            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8')
            stderr_text = stderr.read().decode('utf-8')

            ssh.close()
            return (exit_code, stdout_text, stderr_text)

        except Exception as e:
            logger.error(f"SSH execution failed: {e}")
            return (-1, "", str(e))

    def wait_for_mlnode_ready(self, mlnode_url: str, timeout: int = 1800) -> bool:
        """
        Wait for MLNode to be fully ready (container started, models loaded)

        Args:
            mlnode_url: Base URL of the MLNode instance
            timeout: Maximum time to wait in seconds

        Returns:
            True if MLNode is ready
        """
        logger.info(f"Waiting for MLNode to be ready at {mlnode_url}...")

        start_time = time.time()
        attempt = 0
        health_endpoint = f"{mlnode_url}{self.mlnode_api_segment}/state"

        while (time.time() - start_time) < timeout:
            attempt += 1
            try:
                response = requests.get(health_endpoint, timeout=10)

                if response.status_code == 200:
                    state_data = response.json()
                    state = state_data.get('state', 'UNKNOWN')

                    if attempt % 6 == 0:
                        elapsed = int(time.time() - start_time)
                        logger.info(f"MLNode state: {state} ({elapsed}s elapsed)")

                    # MLNode is ready when it's in a stable state
                    if state in ['STOPPED', 'INFERENCE', 'POW']:
                        logger.info(f"✅ MLNode is ready (state: {state})")
                        return True

            except requests.RequestException:
                if attempt % 12 == 0:
                    elapsed = int(time.time() - start_time)
                    remaining = max(0, (timeout - elapsed) // 60)
                    logger.info(f"Waiting for MLNode... ({elapsed}s elapsed, ~{remaining}m remaining)")

            time.sleep(5)

        elapsed = int(time.time() - start_time)
        logger.error(f"MLNode failed to be ready after {elapsed}s")
        return False

    def start_mlnode_container(self, ssh_info: Dict, instance_id: int) -> Optional[str]:
        """
        Wait for the official MLNode Docker container to be ready on the remote GPU.
        The container is already running (started by Vast.ai), we just need to
        wait for the MLNode API to become accessible.

        Args:
            ssh_info: Connection details (contains host/port info)
            instance_id: Vast.ai instance ID

        Returns:
            MLNode base URL if successful
        """
        logger.info("Waiting for MLNode container to be ready on remote GPU...")
        logger.info("Note: MLNode Docker image does not include SSH - checking API only")

        # Build MLNode URL from connection info
        mlnode_host = ssh_info['host']
        mlnode_port = ssh_info.get('mlnode_port', self.mlnode_port)  # Use mapped port
        mlnode_url = f"http://{mlnode_host}:{mlnode_port}"

        logger.info(f"MLNode URL: {mlnode_url}")
        logger.info("Waiting for MLNode API to become accessible...")
        logger.info("This may take 15-30 minutes for model download and initialization")

        # Wait for MLNode API to be ready
        # Note: Vast.ai instance IS the MLNode container already running
        # The container exposes port 5070 internally, but Vast.ai maps it to an external port
        if not self.wait_for_mlnode_ready(mlnode_url, timeout=self.mlnode_startup_timeout):
            logger.error("MLNode failed to start within timeout")
            logger.error(f"Timeout: {self.mlnode_startup_timeout}s ({self.mlnode_startup_timeout//60} minutes)")
            logger.error(f"Try checking Vast.ai console for instance {instance_id}")
            return None

        logger.info(f"✅ MLNode is ready at {mlnode_url}")
        return mlnode_url

    def register_mlnode(self, mlnode_url: str, instance_id: int) -> bool:
        """
        Register MLNode with the Gonka Network Node

        Args:
            mlnode_url: Base URL of the MLNode instance
            instance_id: Vast.ai instance ID (used for unique node ID)

        Returns:
            True if successful
        """
        logger.info("Registering MLNode with Network Node...")

        node_id = f"vastai-mlnode-{instance_id}"
        mlnode_host = mlnode_url.split('://')[-1].split(':')[0]

        payload = {
            "id": node_id,
            "host": mlnode_host,
            "inference_port": self.mlnode_port,
            "inference_segment": self.mlnode_inference_segment,
            "poc_port": self.mlnode_port,
            "poc_segment": self.mlnode_api_segment,
            "max_concurrent": 100,
            "models": {
                self.poc_model: {
                    "args": []
                }
            },
            "hardware": [
                {"type": self.hardware_type, "count": self.hardware_count}
            ]
        }

        try:
            logger.info(f"Registration payload:\n{json.dumps(payload, indent=2)}")

            response = requests.post(
                f"{self.admin_api_url}/admin/v1/nodes",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )

            response.raise_for_status()

            result = response.json()
            logger.info(f"✅ MLNode registered: {node_id}")
            logger.info(f"Response: {result}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to register MLNode: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False

    def unregister_mlnode(self, instance_id: int) -> bool:
        """Unregister MLNode from the Network Node"""
        node_id = f"vastai-mlnode-{instance_id}"
        logger.info(f"Unregistering MLNode {node_id}...")

        try:
            response = requests.delete(
                f"{self.admin_api_url}/admin/v1/nodes/{node_id}",
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                logger.info(f"✅ MLNode {node_id} unregistered")
                return True
            else:
                logger.warning(f"Unregister returned: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to unregister: {e}")
            return False

    def wait_for_poc_completion(self, instance_id: int, timeout: int = 900) -> bool:
        """
        Monitor PoC progress via Network Node admin API

        Args:
            instance_id: Vast.ai instance ID
            timeout: Maximum time to wait in seconds

        Returns:
            True if PoC completed successfully
        """
        logger.info(f"Monitoring PoC progress for instance {instance_id}...")

        start_time = time.time()
        check_count = 0
        node_id = f"vastai-mlnode-{instance_id}"
        last_status = None

        while (time.time() - start_time) < timeout:
            check_count += 1
            try:
                response = requests.get(
                    f"{self.admin_api_url}/admin/v1/nodes",
                    timeout=10
                )

                if response.status_code == 200:
                    nodes = response.json()

                    for node_data in nodes:
                        node_info = node_data.get('node', {})
                        if node_info.get('id') == node_id:
                            state = node_data.get('state', {})
                            poc_status = state.get('poc_current_status', 'UNKNOWN')

                            if poc_status != last_status:
                                logger.info(f"PoC Status: {poc_status}")
                                last_status = poc_status

                            # PoC is complete when MLNode returns to IDLE or STOPPED
                            # The Network Node will have received the callbacks
                            if poc_status in ['IDLE', 'STOPPED']:
                                logger.info("✅ PoC completed!")
                                return True

                            # Check if PoC is actually running
                            if check_count == 1 and poc_status == 'IDLE':
                                logger.warning("⚠️ PoC shows IDLE immediately - may not have started")

            except Exception as e:
                if check_count % 5 == 0:
                    logger.error(f"Error checking status: {e}")

            time.sleep(30)

        logger.warning(f"PoC monitoring timed out after {timeout}s")
        return False

    def check_mlnode_health(self, mlnode_url: str) -> Dict:
        """Check MLNode health and status"""
        status = {
            "healthy": False,
            "state": "UNKNOWN",
            "error": None
        }

        try:
            response = requests.get(
                f"{mlnode_url}{self.mlnode_api_segment}/state",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                status["healthy"] = True
                status["state"] = data.get('state', 'UNKNOWN')
            else:
                status["error"] = f"HTTP {response.status_code}"

        except Exception as e:
            status["error"] = str(e)

        return status


def test_manager():
    """Test MLNode PoC Manager"""
    print("\n" + "="*60)
    print("  MLNode PoC Manager - Test")
    print("="*60 + "\n")

    try:
        manager = MLNodePoCManager()

        print("✅ Manager initialized")
        print(f"\nConfiguration:")
        print(f"  Admin API: {manager.admin_api_url}")
        print(f"  SSH Key: {manager.ssh_key_path}")
        print(f"  PoC Model: {manager.poc_model}")
        print(f"  MLNode Port: {manager.mlnode_port}")

        # Check SSH key
        if os.path.exists(manager.ssh_key_path):
            print(f"  ✅ SSH key found")
        else:
            print(f"  ❌ SSH key not found at {manager.ssh_key_path}")

        # Check Network Node API
        try:
            response = requests.get(f"{manager.admin_api_url}/admin/v1/nodes", timeout=5)
            if response.status_code == 200:
                nodes = response.json()
                print(f"  ✅ Network Node API accessible")
                print(f"  Registered nodes: {len(nodes)}")

                if len(nodes) > 0:
                    print(f"\n  Currently registered nodes:")
                    for node_data in nodes:
                        node = node_data.get('node', {})
                        print(f"    • {node.get('id')} - {node.get('host')}:{node.get('inference_port')}")
            else:
                print(f"  ⚠️ API returned: {response.status_code}")
        except Exception as e:
            print(f"  ❌ Cannot reach Network Node API: {e}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = test_manager()
    sys.exit(0 if success else 1)
