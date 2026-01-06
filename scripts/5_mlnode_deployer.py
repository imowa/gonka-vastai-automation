#!/usr/bin/env python3
"""
MLNode Deployer
Deploys Gonka MLNode on Vast.ai GPU instances and integrates with Network Node
"""

import os
import time
import json
import logging
import paramiko
import requests
from typing import Optional, Dict
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VastConnection:
    """SSH connection info for Vast.ai instance"""
    host: str
    port: int
    username: str = "root"


class MLNodeDeployer:
    """Deploys and manages Gonka MLNode on Vast.ai GPU instances"""
    
    def __init__(self):
        # Network Node configuration
        self.network_node_url = os.getenv('GONKA_NETWORK_NODE_URL', 'http://167.71.86.126:8000')
        self.admin_api_url = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')
        self.host_address = os.getenv('GONKA_HOST_ADDRESS')
        
        # MLNode configuration
        self.mlnode_image = os.getenv('MLNODE_DOCKER_IMAGE', 'ghcr.io/product-science/mlnode:3.0.11-post1')
        self.mlnode_model = os.getenv('MLNODE_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        self.mlnode_vllm_args = os.getenv('MLNODE_VLLM_ARGS', '--quantization fp8 --gpu-memory-utilization 0.9')
        
        # SSH configuration
        self.ssh_key_path = os.path.expanduser(os.getenv('VASTAI_SSH_KEY_PATH', '~/.ssh/id_rsa'))
        
        logger.info("MLNode Deployer initialized")
        logger.info(f"Network Node: {self.network_node_url}")
        logger.info(f"Admin API: {self.admin_api_url}")
        logger.info(f"Host Address: {self.host_address}")
    
    def get_instance_ssh_info(self, vastai_manager, instance_id: int) -> Optional[VastConnection]:
        """
        Get SSH connection info from Vast.ai instance
        
        Args:
            vastai_manager: VastAIManager instance
            instance_id: Vast.ai instance ID
        
        Returns:
            VastConnection object or None
        """
        logger.info(f"Getting SSH info for instance {instance_id}...")
        
        try:
            status = vastai_manager.get_instance_status(instance_id)
            
            if not status:
                logger.error("Could not get instance status")
                return None
            
            # Extract SSH info
            ssh_host = status.get('ssh_host')
            ssh_port = status.get('ssh_port')
            
            if not ssh_host or not ssh_port:
                logger.error(f"SSH info not available: {status}")
                return None
            
            connection = VastConnection(
                host=ssh_host,
                port=int(ssh_port)
            )
            
            logger.info(f"SSH: {connection.username}@{connection.host}:{connection.port}")
            return connection
        
        except Exception as e:
            logger.error(f"Failed to get SSH info: {e}")
            return None
    
    def ssh_execute(self, connection: VastConnection, command: str, timeout: int = 300) -> tuple:
        """
        Execute command via SSH
        
        Returns:
            (exit_code, stdout, stderr)
        """
        try:
            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Load SSH key
            if not os.path.exists(self.ssh_key_path):
                logger.error(f"SSH key not found: {self.ssh_key_path}")
                return (-1, "", "SSH key not found")
            
            private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_path)
            
            # Connect
            logger.debug(f"Connecting to {connection.host}:{connection.port}...")
            ssh.connect(
                hostname=connection.host,
                port=connection.port,
                username=connection.username,
                pkey=private_key,
                timeout=30,
                banner_timeout=30
            )
            
            # Execute command
            logger.debug(f"Executing: {command[:100]}...")
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8')
            stderr_text = stderr.read().decode('utf-8')
            
            ssh.close()
            
            return (exit_code, stdout_text, stderr_text)
        
        except Exception as e:
            logger.error(f"SSH execution failed: {e}")
            return (-1, "", str(e))
    
    def deploy_mlnode(self, connection: VastConnection, node_id: str = "vastai-mlnode") -> bool:
        """
        Deploy Gonka MLNode on Vast.ai instance
        
        Args:
            connection: SSH connection info
            node_id: Unique identifier for this MLNode
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Deploying MLNode {node_id} on {connection.host}...")
        
        # Step 1: Check GPU
        logger.info("Step 1: Checking GPU...")
        exit_code, stdout, stderr = self.ssh_execute(connection, "nvidia-smi")
        
        if exit_code != 0:
            logger.error(f"GPU check failed: {stderr}")
            return False
        
        logger.info("✅ GPU detected")
        
        # Step 2: Pull Docker image
        logger.info(f"Step 2: Pulling Docker image {self.mlnode_image}...")
        exit_code, stdout, stderr = self.ssh_execute(
            connection,
            f"docker pull {self.mlnode_image}",
            timeout=600
        )
        
        if exit_code != 0:
            logger.error(f"Docker pull failed: {stderr}")
            return False
        
        logger.info("✅ Docker image pulled")
        
        # Step 3: Create Docker run command
        logger.info("Step 3: Starting MLNode container...")
        
        # Parse vLLM args
        vllm_args = self.mlnode_vllm_args.split()
        
        docker_cmd = f"""docker run -d \
            --name mlnode-{node_id} \
            --gpus all \
            --ipc host \
            -p 8080:8080 \
            -p 5000:5000 \
            -e HF_HOME=/root/.cache \
            -e VLLM_ATTENTION_BACKEND=FLASHINFER \
            {self.mlnode_image} \
            uvicorn api.app:app --host=0.0.0.0 --port=8080
        """
        
        exit_code, stdout, stderr = self.ssh_execute(connection, docker_cmd)
        
        if exit_code != 0:
            logger.error(f"MLNode start failed: {stderr}")
            return False
        
        container_id = stdout.strip()
        logger.info(f"✅ MLNode container started: {container_id[:12]}")
        
        # Step 4: Wait for MLNode to be ready
        logger.info("Step 4: Waiting for MLNode to be ready...")
        
        for i in range(60):  # Wait up to 5 minutes
            time.sleep(5)
            
            # Check if container is still running
            exit_code, stdout, stderr = self.ssh_execute(
                connection,
                f"docker ps -q --filter name=mlnode-{node_id}"
            )
            
            if exit_code != 0 or not stdout.strip():
                logger.error("Container stopped unexpectedly")
                return False
            
            logger.info(f"MLNode starting... ({i*5}s)")
        
        logger.info("✅ MLNode should be ready now")
        return True
    
    def register_mlnode_with_network(
        self,
        connection: VastConnection,
        node_id: str
    ) -> bool:
        """
        Register MLNode with Network Node's admin API
        
        Args:
            connection: SSH connection to MLNode
            node_id: Unique node identifier
        
        Returns:
            True if successful
        """
        logger.info(f"Registering MLNode {node_id} with Network Node...")
        
        # Build registration payload
        payload = {
            "id": node_id,
            "host": f"http://{connection.host}",
            "inference_port": 5000,
            "poc_port": 8080,
            "max_concurrent": 500,
            "models": {
                self.mlnode_model: {
                    "args": self.mlnode_vllm_args.split()
                }
            }
        }
        
        try:
            response = requests.post(
                f"{self.admin_api_url}/admin/v1/nodes",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            
            logger.info(f"✅ MLNode registered with Network Node")
            logger.info(f"Response: {response.json()}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Failed to register MLNode: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return False
    
    def wait_for_poc_completion(self, node_id: str, timeout: int = 900) -> bool:
        """
        Wait for PoC Sprint to complete
        
        Args:
            node_id: MLNode identifier
            timeout: Maximum time to wait in seconds
        
        Returns:
            True if PoC completed successfully
        """
        logger.info(f"Monitoring PoC progress for {node_id}...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Get MLNode status
                response = requests.get(
                    f"{self.admin_api_url}/admin/v1/nodes",
                    timeout=10
                )
                
                if response.status_code == 200:
                    nodes = response.json()
                    
                    # Find our node
                    for node_data in nodes:
                        if node_data.get('node', {}).get('id') == node_id:
                            state = node_data.get('state', {})
                            poc_status = state.get('poc_current_status', 'UNKNOWN')
                            
                            logger.info(f"PoC Status: {poc_status}")
                            
                            # Check if PoC is complete
                            if poc_status == 'IDLE':
                                logger.info("✅ PoC Sprint completed!")
                                return True
                            
                            break
            
            except Exception as e:
                logger.error(f"Error checking PoC status: {e}")
            
            time.sleep(30)  # Check every 30 seconds
        
        logger.warning(f"PoC monitoring timed out after {timeout}s")
        return False
    
    def unregister_mlnode(self, node_id: str) -> bool:
        """Unregister MLNode from Network Node"""
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
                logger.warning(f"Unregister failed: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to unregister: {e}")
            return False
    
    def cleanup_mlnode(self, connection: VastConnection, node_id: str):
        """Stop and remove MLNode container"""
        logger.info(f"Cleaning up MLNode {node_id}...")
        
        # Stop container
        self.ssh_execute(connection, f"docker stop mlnode-{node_id}")
        
        # Remove container
        self.ssh_execute(connection, f"docker rm mlnode-{node_id}")
        
        logger.info("✅ MLNode cleaned up")


def test_deployer():
    """Test MLNode deployer initialization"""
    print("\n" + "="*60)
    print("  MLNode Deployer - Test")
    print("="*60 + "\n")
    
    try:
        deployer = MLNodeDeployer()
        
        print("✅ Deployer initialized")
        print(f"\nConfiguration:")
        print(f"  Network Node: {deployer.network_node_url}")
        print(f"  Admin API: {deployer.admin_api_url}")
        print(f"  Host Address: {deployer.host_address}")
        print(f"  MLNode Image: {deployer.mlnode_image}")
        print(f"  Model: {deployer.mlnode_model}")
        print(f"  SSH Key: {deployer.ssh_key_path}")
        
        # Check SSH key exists
        if os.path.exists(deployer.ssh_key_path):
            print(f"\n✅ SSH key found: {deployer.ssh_key_path}")
        else:
            print(f"\n❌ SSH key not found: {deployer.ssh_key_path}")
        
        # Check Network Node connectivity
        try:
            response = requests.get(f"{deployer.admin_api_url}/admin/v1/nodes", timeout=5)
            if response.status_code == 200:
                print(f"✅ Network Node API accessible")
                nodes = response.json()
                print(f"   Current MLNodes: {len(nodes)}")
            else:
                print(f"⚠️  Network Node API returned: {response.status_code}")
        except Exception as e:
            print(f"❌ Cannot reach Network Node API: {e}")
        
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = test_deployer()
    sys.exit(0 if success else 1)
