#!/usr/bin/env python3
"""
Remote vLLM Manager (Simplified)
Manages remote vLLM instances on Vast.ai GPU
MLNode runs locally on VPS, vLLM runs on rented GPU
"""

import os
import time
import json
import logging
import paramiko
import requests
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RemoteVLLMManager:
    """Manages remote vLLM on Vast.ai GPU, MLNode stays on VPS"""
    
    def __init__(self):
        self.admin_api_url = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')
        self.ssh_key_path = os.path.expanduser(os.getenv('VASTAI_SSH_KEY_PATH', '~/.ssh/id_rsa'))
        self.vllm_model = os.getenv('MLNODE_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        self.inference_port = int(os.getenv('MLNODE_INFERENCE_PORT', '8000'))
        self.poc_port = int(os.getenv('MLNODE_POC_PORT', str(self.inference_port)))
        self.inference_segment = os.getenv('MLNODE_INFERENCE_SEGMENT', '/v1')
        self.poc_segment = os.getenv('MLNODE_POC_SEGMENT', self.inference_segment)
        self.hardware_type = os.getenv('VASTAI_GPU_TYPE', 'RTX_4090')
        self.hardware_count = int(os.getenv('VASTAI_NUM_GPUS', '2'))
        self.ssh_ready_timeout = int(os.getenv('VASTAI_SSH_READY_TIMEOUT', '900'))
        self.ssh_auth_grace = int(os.getenv('VASTAI_SSH_AUTH_GRACE', '300'))
        self.quantization = os.getenv('MLNODE_QUANTIZATION', '').strip()
        self.vllm_startup_timeout = int(os.getenv('VLLM_STARTUP_TIMEOUT', '1800'))
        self.vllm_model_download_timeout = int(os.getenv('VLLM_MODEL_DOWNLOAD_TIMEOUT', '1200'))
        self.vllm_log_path = os.getenv('VLLM_LOG_PATH', '/tmp/vllm.log')
        self.vllm_startup_log_path = os.getenv('VLLM_STARTUP_LOG_PATH', '/tmp/vllm_startup.log')
        self.vllm_pid_path = os.getenv('VLLM_PID_PATH', '/tmp/vllm.pid')
        self.vllm_health_endpoint = os.getenv('VLLM_HEALTH_ENDPOINT', '/v1/health')
        self.vllm_models_endpoint = os.getenv('VLLM_MODELS_ENDPOINT', '/v1/models')
        
        logger.info("Remote vLLM Manager initialized")
        logger.info(
            "SSH ready timeout: %ss (%s minutes)",
            self.ssh_ready_timeout,
            self.ssh_ready_timeout // 60,
        )
        logger.info(
            "vLLM startup timeout: %ss (%s minutes)",
            self.vllm_startup_timeout,
            self.vllm_startup_timeout // 60,
        )
    
    def get_ssh_connection(self, vastai_manager, instance_id: int) -> Optional[Dict]:
        """Get SSH connection details from Vast.ai instance"""
        try:
            # Add delay to avoid rate limiting
            time.sleep(1)
            
            response = vastai_manager.get_instance_status(instance_id)
            if not response:
                logger.error("No response from Vast.ai API")
                return None
            
            # The API wraps instance data in an "instances" key
            status = response.get('instances', {})
            
            if not status:
                logger.error("No instances data in response")
                return None
            
            # Get SSH connection details from the instances object
            ssh_host = status.get('ssh_host')
            ssh_port = status.get('ssh_port', 22)
            
            logger.info(f"🔍 SSH Details from API: host={ssh_host}, port={ssh_port}")
            
            if not ssh_host:
                logger.error(f"SSH host not found in response")
                logger.error(f"Available SSH fields:")
                logger.error(f"  - ssh_host: {status.get('ssh_host')}")
                logger.error(f"  - ssh_port: {status.get('ssh_port')}")
                return None
            
            return {
                'host': ssh_host,
                'port': int(ssh_port),
                'username': 'root'
            }
        except Exception as e:
            logger.error(f"Failed to get SSH info: {e}")
            return None
    
    def wait_for_ssh_ready(self, ssh_info: Dict, max_wait: int = 300) -> bool:
        """
        Wait for SSH to be ready on the remote instance
        
        Args:
            ssh_info: SSH connection details
            max_wait: Maximum time to wait in seconds (default 5 minutes)
        
        Returns:
            True if SSH is ready
        """
        logger.info(f"Waiting for SSH to be ready at {ssh_info['host']}:{ssh_info['port']}...")
        
        start_time = time.time()
        attempt = 0
        auth_failures = 0
        grace_applied = False
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= max_wait:
                if auth_failures > 0 and not grace_applied and self.ssh_auth_grace > 0:
                    max_wait += self.ssh_auth_grace
                    grace_applied = True
                    logger.warning(
                        "SSH auth failures detected; extending SSH ready timeout by %ss (total %ss).",
                        self.ssh_auth_grace,
                        max_wait,
                    )
                else:
                    break

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
                
                # Test SSH connection with a simple command
                stdin, stdout, stderr = ssh.exec_command("echo 'SSH test successful'", timeout=5)
                exit_code = stdout.channel.recv_exit_status()
                
                ssh.close()
                
                if exit_code == 0:
                    logger.info(f"✅ SSH is ready and working (attempt #{attempt})")
                    return True
                else:
                    logger.warning(f"SSH connection established but command failed")
            
            except paramiko.ssh_exception.AuthenticationException:
                auth_failures += 1
                elapsed = int(time.time() - start_time)

                if attempt % 6 == 0:  # Log every 30 seconds
                    logger.info(
                        "SSH auth not ready yet (%ss elapsed, %s auth failures)... Retrying",
                        elapsed,
                        auth_failures,
                    )

                time.sleep(5)
            except Exception as e:
                elapsed = int(time.time() - start_time)
                
                if attempt % 6 == 0:  # Log every 30 seconds
                    logger.info(f"SSH not ready yet ({elapsed}s elapsed)... Retrying")
                
                time.sleep(5)
        
        elapsed = int(time.time() - start_time)
        logger.error(f"SSH failed to be ready after {elapsed}s ({max_wait}s timeout)")
        return False
    
    def ssh_execute(self, ssh_info: Dict, command: str, timeout: int = 300) -> tuple:
        """Execute command via SSH"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_path)
            
            logger.info(f"SSH connecting to {ssh_info['host']}:{ssh_info['port']}...")
            
            ssh.connect(
                hostname=ssh_info['host'],
                port=ssh_info['port'],
                username=ssh_info['username'],
                pkey=private_key,
                timeout=15,
                banner_timeout=30
            )
            
            logger.info(f"✅ SSH connected, executing: {command[:50]}...")
            
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8')
            stderr_text = stderr.read().decode('utf-8')
            
            ssh.close()
            return (exit_code, stdout_text, stderr_text)
        
        except Exception as e:
            logger.error(f"SSH execution failed: {e}")
            return (-1, "", str(e))

    def _tail_remote_log(self, ssh_info: Dict, path: str, lines: int = 50) -> str:
        """Fetch the tail of a remote log file."""
        exit_code, stdout, stderr = self.ssh_execute(
            ssh_info,
            f"tail -{lines} {path} 2>/dev/null || true",
            timeout=10,
        )
        if exit_code != 0:
            logger.debug("Failed to read log %s: %s", path, stderr.strip())
        return stdout.strip()

    def _determine_quantization_flag(self, ssh_info: Dict) -> str:
        """Determine quantization flag for vLLM based on config and GPU capability."""
        if not self.quantization:
            return ""

        quantization_strategy = self.quantization.strip().lower()
        if quantization_strategy != "auto":
            return f"--quantization {self.quantization}"

        logger.info("Auto-detecting quantization strategy based on GPU capability")
        exit_code, stdout, stderr = self.ssh_execute(
            ssh_info,
            "nvidia-smi --query-gpu=name --format=csv,noheader | head -n1",
            timeout=10,
        )
        gpu_name = stdout.strip() if exit_code == 0 else ""
        if gpu_name:
            logger.info("Detected GPU name: %s", gpu_name)
        else:
            logger.warning("Unable to detect GPU name: %s", stderr.strip())

        fp8_supported_gpus = (
            "H100",
            "H200",
            "H800",
            "H20",
            "B100",
            "B200",
        )
        if gpu_name and not any(token in gpu_name for token in fp8_supported_gpus):
            logger.info("GPU does not match FP8-capable list; skipping quantization")
            return ""

        exit_code, stdout, stderr = self.ssh_execute(
            ssh_info,
            "nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1",
            timeout=10,
        )
        if exit_code != 0 or not stdout.strip():
            logger.warning("Unable to detect compute capability: %s", stderr.strip())
            return ""

        try:
            cap_value = float(stdout.strip())
        except ValueError:
            logger.warning("Unexpected compute capability value: %s", stdout.strip())
            return ""

        if cap_value >= 8.9:
            logger.info("Detected compute capability %.1f; enabling fp8 quantization", cap_value)
            return "--quantization fp8"

        logger.info("Compute capability %.1f does not support fp8; skipping quantization", cap_value)
        return ""

    def _build_vllm_start_command(self, quant_flag: str) -> str:
        """Build the vLLM startup command."""
        return (
            "python3 -m vllm.entrypoints.openai.api_server "
            f"--model {self.vllm_model} "
            "--dtype auto "
            f"--port {self.inference_port} "
            "--host 0.0.0.0 "
            f"{quant_flag} "
            "--gpu-memory-utilization 0.9 "
            "--max-num-seqs 256 "
            "--max-model-len 4096"
        )
    
    def start_remote_vllm(self, ssh_info: Dict, instance_id: int) -> Optional[str]:
        """
        Start vLLM on remote GPU
        
        Returns:
            vLLM endpoint URL if successful
        """
        logger.info(f"Starting vLLM on remote GPU...")
        
        # Step 0: Wait for SSH to be ready
        logger.info("Step 0: Waiting for SSH to be ready...")
        if not self.wait_for_ssh_ready(ssh_info, max_wait=self.ssh_ready_timeout):
            logger.error("SSH failed to be ready")
            return None
        
        # Step 1: Check GPU and system
        logger.info("Step 1: Checking system...")
        
        # Fix SSH permissions if needed
        fix_cmd = "chmod 600 /root/.ssh/authorized_keys && chmod 700 /root/.ssh && echo 'Permissions fixed'"
        exit_code, stdout, stderr = self.ssh_execute(ssh_info, fix_cmd, timeout=30)
        if exit_code == 0:
            logger.info("✅ Fixed SSH permissions")
        
        # Check GPU
        exit_code, stdout, stderr = self.ssh_execute(ssh_info, "nvidia-smi")
        if exit_code != 0:
            logger.error(f"No GPU found: {stderr}")
            return None
        
        logger.info("✅ GPU detected")
        logger.info(f"GPU Info:\n{stdout[:200]}...")
        
        # Step 2: Confirm vLLM is installed
        logger.info("Step 2: Validating vLLM installation...")
        exit_code, stdout, stderr = self.ssh_execute(
            ssh_info,
            "python3 -m vllm.entrypoints.openai.api_server --help >/dev/null 2>&1; echo $?",
            timeout=30,
        )
        if stdout.strip() != "0":
            logger.error("vLLM is not available on the remote image. Ensure the Docker image has vLLM installed.")
            return None

        logger.info("✅ vLLM installation detected")

        # Step 3: Start vLLM server
        logger.info("Step 3: Starting vLLM server...")

        # First, kill any existing vLLM processes
        self.ssh_execute(ssh_info, "pkill -f vllm.entrypoints || true", timeout=10)

        quant_flag = self._determine_quantization_flag(ssh_info)
        start_command = self._build_vllm_start_command(quant_flag)

        startup_script = f"""#!/bin/bash
set -e
export PATH=/usr/local/bin:/usr/bin:/bin
echo "Starting vLLM at $(date)" > {self.vllm_startup_log_path}
nohup {start_command} > {self.vllm_log_path} 2>&1 &
echo $! > {self.vllm_pid_path}
echo "vLLM launched with PID $(cat {self.vllm_pid_path})" >> {self.vllm_startup_log_path}
"""

        exit_code, stdout, stderr = self.ssh_execute(ssh_info, startup_script, timeout=60)
        if exit_code != 0:
            logger.error("Failed to start vLLM: %s", stderr)
            return None

        logger.info("✅ vLLM startup initiated")

        # Step 4: Wait for vLLM to be ready
        logger.info("Step 4: Waiting for vLLM to start...")
        poll_interval = 5
        max_attempts = max(1, self.vllm_startup_timeout // poll_interval)
        vllm_ready = False
        startup_start = time.time()

        for i in range(max_attempts):
            time.sleep(poll_interval)

            exit_code, stdout, stderr = self.ssh_execute(
                ssh_info,
                f"test -f {self.vllm_pid_path} && ps -p $(cat {self.vllm_pid_path}) -o pid= || echo 'Not running'",
                timeout=10,
            )

            if "Not running" not in stdout:
                exit_code, stdout, stderr = self.ssh_execute(
                    ssh_info,
                    f"curl -s -f http://localhost:{self.inference_port}{self.vllm_models_endpoint} || "
                    f"curl -s -f http://localhost:{self.inference_port}{self.vllm_health_endpoint} || "
                    "echo 'API not ready'",
                    timeout=10,
                )
                if exit_code == 0 and "API not ready" not in stdout:
                    logger.info("✅ vLLM API is responding!")
                    vllm_ready = True
                    break
            elif i % 12 == 0:
                recent_logs = self._tail_remote_log(ssh_info, self.vllm_log_path, lines=20)
                if recent_logs:
                    logger.warning("vLLM process not running. Recent logs: %s", recent_logs)
                startup_logs = self._tail_remote_log(ssh_info, self.vllm_startup_log_path, lines=50)
                if startup_logs:
                    logger.warning("vLLM startup logs: %s", startup_logs)

            if i % 12 == 0:
                elapsed = int(time.time() - startup_start)
                remaining = max(0, (self.vllm_startup_timeout - elapsed) // 60)
                logger.info("Waiting for vLLM... (%ss elapsed, ~%sm remaining)", elapsed, remaining)

                recent_logs = self._tail_remote_log(ssh_info, self.vllm_log_path, lines=10)
                if recent_logs:
                    logger.info("Recent vLLM logs: %s", recent_logs)

                if elapsed > self.vllm_model_download_timeout:
                    logger.warning(
                        "vLLM still starting after %ss; model download may be slow.",
                        self.vllm_model_download_timeout,
                    )

        if not vllm_ready:
            logger.error("vLLM failed to start in time")

            logger.error("vLLM error logs:\n%s", self._tail_remote_log(ssh_info, self.vllm_log_path, lines=200))
            startup_logs = self._tail_remote_log(ssh_info, self.vllm_startup_log_path, lines=300)
            if startup_logs:
                logger.error("vLLM startup logs:\n%s", startup_logs)
            else:
                logger.error("vLLM startup logs are empty")

            return None
        
        # Return the SSH gateway URL
        vllm_host = ssh_info['host']
        logger.info(f"✅ vLLM is ready at {vllm_host}:{self.inference_port}")
        
        return vllm_host
    
    def register_remote_mlnode(self, vllm_host: str, instance_id: int) -> bool:
        """
        Register remote vLLM as MLNode with Network Node
        
        Args:
            vllm_host: Hostname or IP for remote vLLM
            instance_id: Vast.ai instance ID (for unique node ID)
        
        Returns:
            True if successful
        """
        logger.info(f"Registering remote vLLM as MLNode...")
        
        node_id = f"vastai-{instance_id}"
        
        model_args = []
        if self.quantization and self.quantization.lower() != "auto":
            model_args = ["--quantization", self.quantization]

        payload = {
            "id": node_id,
            "host": vllm_host,
            "inference_port": self.inference_port,
            "inference_segment": self.inference_segment,
            "poc_port": self.poc_port,
            "poc_segment": self.poc_segment,
            "max_concurrent": 100,
            "models": {
                self.vllm_model: {
                    "args": model_args + ["--gpu-memory-utilization", "0.9"]
                }
            },
            "hardware": [
                {"type": self.hardware_type, "count": self.hardware_count}
            ]
        }
        
        try:
            logger.info(f"Sending registration payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(
                f"{self.admin_api_url}/admin/v1/nodes",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Remote MLNode registered: {node_id}")
            logger.info(f"Response: {result}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Failed to register remote MLNode: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False
    
    def unregister_remote_mlnode(self, instance_id: int) -> bool:
        """Unregister remote MLNode from Network Node"""
        node_id = f"vastai-{instance_id}"
        logger.info(f"Unregistering remote MLNode {node_id}...")
        
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
    
    def check_vllm_status(self, ssh_info: Dict) -> Dict:
        """Check vLLM status on remote instance"""
        status = {
            "gpu_available": False,
            "vllm_running": False,
            "vllm_responding": False,
            "logs": ""
        }
        
        try:
            # Check GPU
            exit_code, stdout, stderr = self.ssh_execute(ssh_info, "nvidia-smi", timeout=30)
            if exit_code == 0:
                status["gpu_available"] = True
            
            # Check vLLM process
            exit_code, stdout, stderr = self.ssh_execute(
                ssh_info, 
                "ps aux | grep vllm.entrypoints | grep -v grep",
                timeout=10
            )
            if exit_code == 0 and "python3 -m vllm.entrypoints" in stdout:
                status["vllm_running"] = True
            
            # Check vLLM API
            exit_code, stdout, stderr = self.ssh_execute(
                ssh_info,
                f"curl -s http://localhost:{self.inference_port}{self.vllm_health_endpoint} || echo 'Not healthy'",
                timeout=10
            )
            if exit_code == 0 and "Not healthy" not in stdout:
                status["vllm_responding"] = True
            
            # Get recent logs
            exit_code, stdout, stderr = self.ssh_execute(
                ssh_info,
                f"tail -20 {self.vllm_log_path} 2>/dev/null || echo 'No logs'",
                timeout=10
            )
            status["logs"] = stdout.strip()
            
        except Exception as e:
            logger.error(f"Error checking vLLM status: {e}")
        
        return status
    
    def stop_remote_vllm(self, ssh_info: Dict):
        """Stop vLLM on remote GPU"""
        logger.info("Stopping remote vLLM...")
        
        try:
            # Kill vLLM process
            self.ssh_execute(ssh_info, "pkill -f vllm.entrypoints", timeout=10)
            self.ssh_execute(ssh_info, "pkill -f start_vllm.sh", timeout=10)
            
            # Clean up PID file
            self.ssh_execute(ssh_info, f"rm -f {self.vllm_pid_path}", timeout=5)
            
            logger.info("✅ vLLM stopped")
        except Exception as e:
            logger.warning(f"Error stopping vLLM: {e}")
    
    def wait_for_poc_completion(self, instance_id: int, timeout: int = 900) -> bool:
        """
        Monitor PoC progress via local MLNode API
        
        Returns:
            True if PoC completed successfully
        """
        logger.info(f"Monitoring PoC progress for instance {instance_id}...")
        
        start_time = time.time()
        check_count = 0
        node_id = f"vastai-{instance_id}"
        
        while time.time() - start_time < timeout:
            check_count += 1
            try:
                # Check MLNode status
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
                            
                            if check_count % 5 == 0:
                                logger.info(f"PoC Status for {node_id}: {poc_status}")
                            
                            if poc_status == 'IDLE':
                                logger.info("✅ PoC completed!")
                                return True
            
            except Exception as e:
                if check_count % 5 == 0:
                    logger.error(f"Error checking status: {e}")
            
            time.sleep(30)
        
        logger.warning(f"PoC monitoring timed out after {timeout}s")
        return False


def test_manager():
    """Test remote vLLM manager"""
    print("\n" + "="*60)
    print("  Remote vLLM Manager - Test")
    print("="*60 + "\n")
    
    try:
        manager = RemoteVLLMManager()
        
        print("✅ Manager initialized")
        print(f"\nConfiguration:")
        print(f"  Admin API: {manager.admin_api_url}")
        print(f"  SSH Key: {manager.ssh_key_path}")
        print(f"  Model: {manager.vllm_model}")
        
        # Check SSH key
        if os.path.exists(manager.ssh_key_path):
            print(f"  ✅ SSH key found")
        else:
            print(f"  ❌ SSH key not found")
        
        # Check local MLNode
        try:
            response = requests.get(f"{manager.admin_api_url}/admin/v1/nodes", timeout=5)
            if response.status_code == 200:
                nodes = response.json()
                print(f"  ✅ Network Node API accessible")
                print(f"  Registered MLNodes: {len(nodes)}")
                
                if len(nodes) > 0:
                    print(f"\n  Registered MLNodes:")
                    for node in nodes:
                        node_info = node.get('node', {})
                        print(f"    ID: {node_info.get('id')}")
                        print(f"    Host: {node_info.get('host')}")
            else:
                print(f"  ⚠️  API returned: {response.status_code}")
        except Exception as e:
            print(f"  ❌ Cannot reach API: {e}")
        
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = test_manager()
    sys.exit(0 if success else 1)
