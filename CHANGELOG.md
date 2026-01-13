# Changelog

## Unreleased
- Default Vast.ai rentals to the official Gonka MLNode image via `DOCKER_IMAGE`.
- Simplified remote vLLM startup to skip installation and harden readiness checks.
- Added FP8-capable GPU filtering when auto quantization is enabled.
- Expanded timeouts and logging for SSH and vLLM startup to reduce flaky PoC runs.
- Updated environment example and documentation for new Docker/Vast.ai settings.
