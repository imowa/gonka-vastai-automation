#!/usr/bin/env python3
"""
Deploy Hybrid MLNode System
Integrates with your existing Gonka Network Node
"""

import os
import time
import json
import logging
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HybridDeployer:
    """Deploy hybrid MLNode system"""
    
    def __init__(self):
        # Configuration
        self.network_node_url = os.getenv('GONKA_NETWORK_NODE_URL', 'http://167.71.86.126:8000')
        self.admin_api_url = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')
        self.hyperbolic_api_key = os.getenv('HYPERBOLIC_API_KEY')
        self.vastai_api_key = os.getenv('VASTAI_API_KEY')
        
        # Paths
        self.gonka_path = Path.home() / "gonka"
        self.automation_path = Path.home() / "gonka-vastai-automation"
        
        logger.info("Hybrid Deployer initialized")
    
    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        logger.info("Checking prerequisites...")
        
        checks = []
        
        # Check API keys
        if self.hyperbolic_api_key:
            logger.info("✅ Hyperbolic API key found")
            checks.append(True)
        else:
            logger.error("❌ HYPERBOLIC_API_KEY missing")
            checks.append(False)
        
        if self.vastai_api_key:
            logger.info("✅ Vast.ai API key found") 
            checks.append(True)
        else:
            logger.error("❌ VASTAI_API_KEY missing")
            checks.append(False)
        
        # Check Gonka installation
        if self.gonka_path.exists():
            logger.info(f"✅ Gonka found at {self.gonka_path}")
            checks.append(True)
        else:
            logger.error(f"❌ Gonka not found at {self.gonka_path}")
            checks.append(False)
        
        # Check automation repo
        if self.automation_path.exists():
            logger.info(f"✅ Automation repo found at {self.automation_path}")
            checks.append(True)
        else:
            logger.error(f"❌ Automation repo not found at {self.automation_path}")
            checks.append(False)
        
        # Test Hyperbolic API
        try:
            import sys
            sys.path.append(str(self.automation_path / "scripts"))
            from hyperbolic_runner import HyperbolicAPIRunner
            
            hyperbolic = HyperbolicAPIRunner(api_key=self.hyperbolic_api_key)
            if hyperbolic.health_check():
                logger.info("✅ Hyperbolic API accessible")
                checks.append(True)
            else:
                logger.error("❌ Hyperbolic API not accessible")
                checks.append(False)
        except Exception as e:
            logger.error(f"❌ Hyperbolic API test failed: {e}")
            checks.append(False)
        
        # Test Network Node connectivity
        try:
            response = requests.get(f"{self.admin_api_url}/admin/v1/nodes", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Network Node admin API accessible")
                checks.append(True)
            else:
                logger.warning(f"⚠️  Network Node returned {response.status_code}")
                checks.append(True)  # Still proceed
        except Exception as e:
            logger.error(f"❌ Network Node not accessible: {e}")
            checks.append(False)
        
        all_good = all(checks)
        logger.info(f"Prerequisites check: {'PASSED' if all_good else 'FAILED'}")
        return all_good
    
    def update_gonka_config(self) -> bool:
        """Update Gonka configuration for hybrid mode"""
        logger.info("Updating Gonka configuration...")
        
        try:
            # Path to node config
            config_path = self.gonka_path / "deploy" / "join" / "node-config.json"
            
            if not config_path.exists():
                logger.error(f"Config file not found: {config_path}")
                return False
            
            # Load current config
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Update for hybrid mode
            for node in config:
                if node.get('id') == 'node1':
                    # Point to our hybrid MLNode
                    node['host'] = 'localhost'  # Since we're on same VPS
                    node['inference_port'] = 5000
                    node['poc_port'] = 8080
                    
                    # Use bigger model for PoC (we'll use Hyperbolic for inference)
                    node['models'] = {
                        "Qwen/Qwen2.5-72B-Instruct": {
                            "args": ["--quantization", "fp8", "--gpu-memory-utilization", "0.9"]
                        }
                    }
                    logger.info("✅ Updated node configuration for hybrid mode")
                    break
            
            # Backup original
            backup_path = config_path.with_suffix('.json.backup')
            if not backup_path.exists():
                with open(backup_path, 'w') as f:
                    json.dump(config, f, indent=2)
                logger.info(f"✅ Backed up original config to {backup_path}")
            
            # Write updated config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("✅ Gonka configuration updated")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update Gonka config: {e}")
            return False
    
    def install_hybrid_dependencies(self) -> bool:
        """Install Python dependencies for hybrid mode"""
        logger.info("Installing hybrid dependencies...")
        
        try:
            # Install required packages
            packages = [
                'fastapi',
                'uvicorn',
                'requests',
                'paramiko',
                'python-dotenv'
            ]
            
            for package in packages:
                subprocess.run(['pip', 'install', package], check=True)
            
            logger.info("✅ Dependencies installed")
            return True
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            return False
    
    def setup_hybrid_service(self) -> bool:
        """Setup hybrid MLNode as a systemd service"""
        logger.info("Setting up hybrid service...")
        
        try:
            # Create service file
            service_content = f"""[Unit]
Description=Gonka Hybrid MLNode
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={self.automation_path}
Environment=PYTHONPATH={self.automation_path}/scripts
ExecStart=/usr/bin/python3 {self.automation_path}/scripts/6_hybrid_mlnode.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
            
            service_path = Path('/etc/systemd/system/gonka-hybrid.service')
            
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            
            logger.info("✅ Service file created")
            logger.info("   To start: sudo systemctl start gonka-hybrid")
            logger.info("   To enable: sudo systemctl enable gonka-hybrid")
            return True
        
        except Exception as e:
            logger.error(f"Failed to setup service: {e}")
            return False
    
    def register_with_network_node(self) -> bool:
        """Register hybrid MLNode with Network Node"""
        logger.info("Registering with Network Node...")
        
        try:
            # Registration payload
            payload = {
                "id": "hybrid-mlnode",
                "host": "http://localhost",
                "inference_port": 5000,
                "poc_port": 8080,
                "max_concurrent": 1000,
                "models": {
                    "Qwen/Qwen2.5-72B-Instruct": {
                        "args": ["--quantization", "fp8", "--gpu-memory-utilization", "0.9"]
                    }
                }
            }
            
            response = requests.post(
                f"{self.admin_api_url}/admin/v1/nodes",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("✅ Successfully registered with Network Node")
                logger.info(f"Response: {response.json()}")
                return True
            else:
                logger.error(f"Registration failed: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False
    
    def deploy(self) -> bool:
        """Deploy the complete hybrid system"""
        logger.info("Starting hybrid MLNode deployment...")
        
        steps = [
            ("Prerequisites", self.check_prerequisites),
            ("Install Dependencies", self.install_hybrid_dependencies),
            ("Update Gonka Config", self.update_gonka_config),
            ("Setup Service", self.setup_hybrid_service),
        ]
        
        for step_name, step_func in steps:
            logger.info(f"\n{'='*50}")
            logger.info(f"Step: {step_name}")
            logger.info(f"{'='*50}")
            
            if not step_func():
                logger.error(f"❌ Step failed: {step_name}")
                return False
            
            logger.info(f"✅ Step completed: {step_name}")
        
        logger.info("\n" + "="*60)
        logger.info("  DEPLOYMENT COMPLETE")
        logger.info("="*60)
        
        logger.info("\n📋 Next steps:")
        logger.info("1. Copy 6_hybrid_mlnode.py to your automation repo/scripts/")
        logger.info("2. Start the hybrid service:")
        logger.info("   sudo systemctl start gonka-hybrid")
        logger.info("3. Enable auto-start:")
        logger.info("   sudo systemctl enable gonka-hybrid")
        logger.info("4. Monitor logs:")
        logger.info("   journalctl -u gonka-hybrid -f")
        logger.info("5. Register with Network Node (after service is running)")
        
        return True

def main():
    """Main deployment function"""
    print("\n" + "="*60)
    print("  Gonka Hybrid MLNode Deployment")
    print("="*60)
    print("\nThis will set up:")
    print("  ✅ Hyperbolic API for inference")
    print("  ✅ Vast.ai GPU bursts for PoC")
    print("  ✅ Integration with your Network Node")
    
    deployer = HybridDeployer()
    
    try:
        success = deployer.deploy()
        
        if success:
            print("\n🎉 Deployment successful!")
            print("\n💰 Expected monthly costs:")
            print("   • Hyperbolic inference: $12-60/month")
            print("   • Vast.ai PoC bursts: $1-3/month") 
            print("   • Total: $13-63/month (vs $500+ for 24/7 GPU)")
            
            return True
        else:
            print("\n❌ Deployment failed!")
            return False
    
    except Exception as e:
        print(f"\n❌ Deployment error: {e}")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
