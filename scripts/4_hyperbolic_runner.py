#!/usr/bin/env python3
"""
Hyperbolic API Runner
Handles inference requests via Hyperbolic API as a drop-in replacement for vLLM.
This runs 24/7 and serves inference while PoC uses GPU rental.
"""

import os
import json
import logging
from typing import Optional, Dict, List, Iterator
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents a chat message"""
    role: str  # system, user, assistant
    content: str


class HyperbolicAPIRunner:
    """
    Drop-in replacement for vLLM using Hyperbolic API
    Implements OpenAI-compatible interface
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv('HYPERBOLIC_API_KEY')
        self.base_url = base_url or os.getenv('HYPERBOLIC_BASE_URL', 'https://api.hyperbolic.xyz/v1')
        self.model = model or os.getenv('HYPERBOLIC_MODEL', 'meta-llama/Llama-3.3-70B-Instruct')
        
        if not self.api_key:
            raise ValueError("HYPERBOLIC_API_KEY not found in environment")
        
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        logger.info("Hyperbolic API Runner initialized")
        logger.info(f"Model: {self.model}")
        logger.info(f"Base URL: {self.base_url}")
    
    def chat_completion(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs
    ) -> Dict:
        """
        Create a chat completion
        
        Args:
            messages: List of chat messages
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional parameters
        
        Returns:
            Response dict in OpenAI format
        """
        url = f"{self.base_url}/chat/completions"
        
        # Convert messages to dict format
        messages_dict = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        payload = {
            "model": self.model,
            "messages": messages_dict,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs
        }
        
        try:
            if stream:
                return self._stream_completion(url, payload)
            else:
                response = requests.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                return response.json()
        
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def _stream_completion(self, url: str, payload: Dict) -> Iterator[Dict]:
        """Stream completion responses"""
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]  # Remove 'data: ' prefix
                        if data == '[DONE]':
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        
        except requests.RequestException as e:
            logger.error(f"Streaming failed: {e}")
            raise
    
    def completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs
    ) -> Dict:
        """
        Create a text completion (non-chat)
        
        Args:
            prompt: Input prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream
            **kwargs: Additional parameters
        
        Returns:
            Response dict
        """
        # Convert to chat format
        messages = [ChatMessage(role="user", content=prompt)]
        return self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs
        )
    
    def get_models(self) -> List[str]:
        """List available models"""
        url = f"{self.base_url}/models"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and 'data' in data:
                return [model['id'] for model in data['data']]
            return []
        
        except requests.RequestException as e:
            logger.error(f"Failed to fetch models: {e}")
            return []
    
    def health_check(self) -> bool:
        """Check if API is accessible"""
        try:
            models = self.get_models()
            return len(models) > 0
        except Exception:
            return False


class HyperbolicInferenceServer:
    """
    Simple inference server that mimics Gonka MLNode interface
    This would run on port 5000 (same as vLLM) but uses Hyperbolic API
    """
    
    def __init__(self):
        self.runner = HyperbolicAPIRunner()
        logger.info("Hyperbolic Inference Server initialized")
    
    def handle_chat_completion(self, request_data: Dict) -> Dict:
        """Handle /v1/chat/completions endpoint"""
        messages = [
            ChatMessage(role=msg['role'], content=msg['content'])
            for msg in request_data.get('messages', [])
        ]
        
        temperature = request_data.get('temperature', 0.7)
        max_tokens = request_data.get('max_tokens', 2048)
        stream = request_data.get('stream', False)
        
        return self.runner.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
    
    def handle_completion(self, request_data: Dict) -> Dict:
        """Handle /v1/completions endpoint"""
        prompt = request_data.get('prompt', '')
        temperature = request_data.get('temperature', 0.7)
        max_tokens = request_data.get('max_tokens', 2048)
        stream = request_data.get('stream', False)
        
        return self.runner.completion(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )


def test_basic_completion():
    """Test 1: Basic completion"""
    print("\n" + "="*60)
    print("  TEST 1: Basic Text Completion")
    print("="*60 + "\n")
    
    try:
        runner = HyperbolicAPIRunner()
        
        response = runner.completion(
            prompt="What is the capital of France?",
            max_tokens=50
        )
        
        print("✅ API connection successful")
        print(f"\nPrompt: What is the capital of France?")
        print(f"Response: {response['choices'][0]['text'][:200]}")
        
        # Show usage stats
        if 'usage' in response:
            usage = response['usage']
            print(f"\nTokens used:")
            print(f"  Prompt: {usage.get('prompt_tokens', 0)}")
            print(f"  Completion: {usage.get('completion_tokens', 0)}")
            print(f"  Total: {usage.get('total_tokens', 0)}")
        
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_chat_completion():
    """Test 2: Chat completion"""
    print("\n" + "="*60)
    print("  TEST 2: Chat Completion")
    print("="*60 + "\n")
    
    try:
        runner = HyperbolicAPIRunner()
        
        messages = [
            ChatMessage(role="system", content="You are a helpful AI assistant."),
            ChatMessage(role="user", content="Explain quantum computing in one sentence.")
        ]
        
        response = runner.chat_completion(
            messages=messages,
            max_tokens=100,
            temperature=0.7
        )
        
        print("✅ Chat completion successful")
        print(f"\nUser: Explain quantum computing in one sentence.")
        print(f"Assistant: {response['choices'][0]['message']['content']}")
        
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_streaming():
    """Test 3: Streaming response"""
    print("\n" + "="*60)
    print("  TEST 3: Streaming Response")
    print("="*60 + "\n")
    
    try:
        runner = HyperbolicAPIRunner()
        
        messages = [
            ChatMessage(role="user", content="Count from 1 to 5.")
        ]
        
        print("User: Count from 1 to 5.")
        print("Assistant: ", end="", flush=True)
        
        response_stream = runner.chat_completion(
            messages=messages,
            max_tokens=50,
            stream=True
        )
        
        for chunk in response_stream:
            if 'choices' in chunk and len(chunk['choices']) > 0:
                delta = chunk['choices'][0].get('delta', {})
                if 'content' in delta:
                    print(delta['content'], end="", flush=True)
        
        print("\n\n✅ Streaming successful")
        return True
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


def test_models_list():
    """Test 4: List available models"""
    print("\n" + "="*60)
    print("  TEST 4: Available Models")
    print("="*60 + "\n")
    
    try:
        runner = HyperbolicAPIRunner()
        models = runner.get_models()
        
        if models:
            print("✅ Available models:")
            for model in models[:5]:  # Show first 5
                print(f"  - {model}")
            if len(models) > 5:
                print(f"  ... and {len(models) - 5} more")
            return True
        else:
            print("⚠️  No models found (API might not support listing)")
            return True  # Not a failure
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  Hyperbolic API Runner - Test Suite")
    print("="*60)
    
    tests = [
        ("Basic Completion", test_basic_completion),
        ("Chat Completion", test_chat_completion),
        ("Streaming", test_streaming),
        ("Models List", test_models_list),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60 + "\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        print("\n" + "="*60)
        print("  Hyperbolic API Runner is Ready!")
        print("="*60)
        print("\nYou can now use Hyperbolic API for inference!")
        print("\nEstimated costs (approximate):")
        print("  - $0.50-1.00 per 1M tokens")
        print("  - Typical usage: $20-40/month")
        print("\nTotal monthly cost (PoC + Inference):")
        print("  - PoC GPU: ~$1-2/month")
        print("  - Hyperbolic: ~$20-40/month")
        print("  - TOTAL: ~$21-42/month 🎉")
    else:
        print("\n⚠️  Some tests failed")
        print("\nMake sure you have:")
        print("  1. HYPERBOLIC_API_KEY in config/.env")
        print("  2. Valid API key from Hyperbolic")
        print("  3. Internet connection")
    
    return passed == total


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
