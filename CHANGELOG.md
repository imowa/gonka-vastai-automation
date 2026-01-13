# Changelog

## Unreleased
- Default Vast.ai rentals to the prebuilt `vllm/vllm-openai:latest` image for faster startup.
- Simplified remote vLLM startup by assuming the image includes vLLM and improving readiness checks.
- Added configurable timeouts and logging for SSH and vLLM startup to reduce flaky PoC runs.
- Added CLI overrides for Docker image and vLLM startup timeout in `test_live_poc.py`.
- Updated environment example and documentation for new Vast.ai and vLLM settings.
