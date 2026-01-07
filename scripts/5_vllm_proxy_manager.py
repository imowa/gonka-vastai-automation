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
        
        logger.info("Remote vLLM Manager initialized")
    
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
            # IMPORTANT: Use ssh_host (ssh3.vast.ai) NOT public_ipaddr!
            ssh_host = status.get('ssh_host')
            ssh_port = status.get('ssh_port', 22)
            
            logger.info(f"🔍 SSH Details from API: host={ssh_host}, port={ssh_port}")
            
            if not ssh_host:
                logger.error(f"SSH host not found in response")
                logger.error(f"Available SSH fields:")
                logger.error(f"  - ssh_host: {status.get('ssh_host')}")
                logger.error(f"  - ssh_port: {status.get('ssh_port')}")
                logger.error(f"  - public_ipaddr: {status.get('public_ipaddr')}")
                return None
            
            return {
                'host': ssh_host,
                'port': int(ssh_port),
                'username': 'root'
            }
        except Exception as e:
            logger.error(f"Failed to get SSH info: {e}")
            return None
    
    def wait_for_ssh_ready(self, ssh_info: Dict, max_wait: int = 600) -> bool:
        """
        Wait for SSH to be ready on the remote instance
        Account for 13GB+ Docker image download time
        
        Args:
            ssh_info: SSH connection details
            max_wait: Maximum time to wait in seconds (default 10 minutes for large image)
        
        Returns:
            True if SSH is ready
        """
        logger.info(f"Waiting for SSH to be ready at {ssh_info['host']}:{ssh_info['port']}...")
        logger.info(f"This may take several minutes while Docker image (13GB+) is downloaded...")
        
        start_time = time.time()
        attempt = 0
        
        while time.time() - start_time < max_wait:
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
                    timeout=5  # Short timeout for probing
                )
                
                # If we get here, SSH is ready
                ssh.close()
                logger.info(f"✅ SSH is ready (attempt #{attempt})")
                return True
            
            except (paramiko.ssh_exception.NoValidConnectionsError, 
                    paramiko.ssh_exception.AuthenticationException,
                    TimeoutError,
                    Exception) as e:
                elapsed = int(time.time() - start_time)
                
                if attempt % 12 == 0:  # Log every 60 seconds
                    logger.info(f"SSH not ready yet ({elapsed}s elapsed, {(max_wait - elapsed)//60}m remaining)... Retrying")
                
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
                timeout=10  # Increased timeout
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
    
    def start_remote_vllm(self, ssh_info: Dict, instance_id: int) -> Optional[str]:
        """
        Start vLLM on remote GPU
        
        Returns:
            vLLM endpoint URL if successful
        """
        logger.info(f"Starting vLLM on remote GPU...")
        
        # Step 0: Wait for SSH to be ready (with extended timeout for Docker pull)
        logger.info("Step 0: Waiting for SSH to be ready...")
        if not self.wait_for_ssh_ready(ssh_info, max_wait=600):  # 10 minutes for Docker download
            logger.error("SSH failed to be ready")
            return None
        
        # Step 1: Check GPU
        logger.info("Step 1: Checking GPU...")
        exit_code, stdout, stderr = self.ssh_execute(ssh_info, "nvidia-smi")
        if exit_code != 0:
            logger.error(f"No GPU found: {stderr}")
            return None
        
        logger.info("✅ GPU detected")
        logger.info(f"GPU Output:\n{stdout[:200]}")
        
        # Step 2: Check if vLLM is installed
        logger.info("Step 2: Checking vLLM installation...")
        exit_code, stdout, stderr = self.ssh_execute(ssh_info, "python3 -m pip list | grep vllm", timeout=60)
        
        if exit_code != 0:
            logger.warning("vLLM not installed, attempting to install...")
            exit_code, stdout, stderr = self.ssh_execute(
                ssh_info, 
                "pip install vllm==0.5.0 --no-cache-dir",
                timeout=600
            )
            if exit_code != 0:
                logger.error(f"Failed to install vLLM: {stderr}")
                return None
            logger.info("✅ vLLM installed")
        else:
            logger.info("✅ vLLM already installed")
        
        # Step 3: Start vLLM server
        logger.info("Step 3: Starting vLLM server...")
        
        vllm_command = f"""nohup python3 -m vllm.entrypoints.openai.api_server \\
            --model {self.vllm_model} \\
            --dtype auto \\
            --port 8000 \\
            --host 0.0.0.0 \\
            --quantization fp8 \\
            --gpu-memory-utilization 0.9 \\
            > /tmp/vllm.log 2>&1 &
        echo "vLLM started"
        """
        
        exit_code, stdout, stderr = self.ssh_execute(ssh_info, vllm_command, timeout=30)
        
        if exit_code != 0:
            logger.error(f"Failed to start vLLM: {stderr}")
            return None
        
        logger.info("✅ vLLM starting...")
        
        # Step 4: Wait for vLLM to be ready
        vllm_url = f"http://{ssh_info['host']}:8000"
        logger.info(f"Step 4: Waiting for vLLM at {vllm_url}...")
        
        for i in range(60):  # Wait up to 5 minutes
            time.sleep(5)
            try:
                response = requests.get(f"{vllm_url}/v1/models", timeout=5)
                if response.status_code == 200:
                    logger.info("✅ vLLM is ready!")
                    return vllm_url
            except Exception as e:
                if i % 6 == 0:  # Log every 30 seconds
                    logger.info(f"Waiting for vLLM... ({i*5}s elapsed)")
        
        logger.error("vLLM failed to start in time")
        return None
    
    def register_remote_mlnode(self, vllm_url: str, instance_id: int) -> bool:
        """
        Register remote vLLM as MLNode with Network Node
        
        Args:
            vllm_url: URL of remote vLLM server
            instance_id: Vast.ai instance ID (for unique node ID)
        
        Returns:
            True if successful
        """
        logger.info(f"Registering remote vLLM as MLNode...")
        
        node_id = f"vastai-{instance_id}"
        
        # Extract host from URL
        import urllib.parse
        parsed = urllib.parse.urlparse(vllm_url)
        vllm_host = parsed.hostname
        vllm_port = parsed.port or 8000
        
        payload = {
            "id": node_id,
            "host": f"http://{vllm_host}",
            "inference_port": vllm_port,
            "poc_port": vllm_port,
            "max_concurrent": 500,
            "models": {
                self.vllm_model: {
                    "args": ["--quantization", "fp8", "--gpu-memory-utilization", "0.9"]
                }
            }
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
            
            logger.info(f"✅ Remote MLNode registered: {node_id}")
            logger.info(f"Response: {response.json()}")
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
    
    def configure_mlnode_proxy(self, vllm_url: str) -> bool:
        """
        No longer needed - Network Node talks directly to remote vLLM
        Kept for backward compatibility
        """
        logger.info(f"Network Node will connect directly to {vllm_url}")
        return True
    
    def stop_remote_vllm(self, ssh_info: Dict):
        """Stop vLLM on remote GPU"""
        logger.info("Stopping remote vLLM...")
        
        try:
            # Kill vLLM process
            self.ssh_execute(ssh_info, "pkill -f vllm.entrypoints", timeout=10)
            
            logger.info("✅ vLLM stopped")
        except Exception as e:
            logger.warning(f"Error stopping vLLM: {e}")
    
    def wait_for_poc_completion(self, timeout: int = 900) -> bool:
        """
        Monitor PoC progress via local MLNode API
        
        Returns:
            True if PoC completed successfully
        """
        logger.info("Monitoring PoC progress...")
        
        start_time = time.time()
        check_count = 0
        
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
                        state = node_data.get('state', {})
                        poc_status = state.get('poc_current_status', 'UNKNOWN')
                        
                        if check_count % 10 == 0:
                            logger.info(f"PoC Status: {poc_status}")
                        
                        if poc_status == 'IDLE':
                            logger.info("✅ PoC completed!")
                            return True
            
            except Exception as e:
                if check_count % 10 == 0:
                    logger.error(f"Error checking status: {e}")
            
            time.sleep(30)
        
        logger.warning("PoC monitoring timed out")
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
                print(f"  Local MLNodes: {len(nodes)}")
                
                if len(nodes) > 0:
                    print(f"\n  Registered MLNode:")
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