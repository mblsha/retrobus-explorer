# Alchitry CI Container

This directory contains a containerized version of the Alchitry CI environment that mirrors the GitHub Actions setup for local testing.

## Features

- Ubuntu 22.04 base image (matching GitHub Actions)
- Java 22 (OpenJDK) for Alchitry Labs
- Alchitry Labs V2 pre-installed
- Automated project syntax checking and test bench execution

## Requirements

- Container runtime: Either Docker or Apple Container (`container` command)

## Quick Start

1. Build the container:
   ```bash
   # For Apple Container runtime:
   ./.github/container/build.sh
   
   # For Docker:
   ./.github/container/docker-build.sh
   ```

2. Test all projects:
   ```bash
   ./.github/container/test.sh  # Automatically detects Docker or container runtime
   ```

3. Test specific projects:
   ```bash
   ./.github/container/test.sh test-minimal pin-tester
   ```

## Manual Usage

Run an interactive shell in the container:
```bash
container run --rm -it \
    --volume "$(pwd):/workspace" \
    retrobus-alchitry-ci
```

Check a specific project manually:
```bash
container run --rm \
    --volume "$(pwd):/workspace" \
    retrobus-alchitry-ci \
    bash -c "cd /workspace/gateware/test-minimal && \$ALCHITRY_BIN check test-minimal.alp"
```

## Architecture Note

The container runs natively on ARM64 (Apple Silicon) using Java 22, which is required by the latest Alchitry Labs version.

## Files

- `Dockerfile` - Container definition with Java 22 and Alchitry Labs
- `build.sh` - Script to build the container image (Apple Container runtime)
- `docker-build.sh` - Script to build the container image (Docker)
- `test.sh` - Script to run CI checks locally (works with both runtimes)
- `README.md` - This documentation

## GitHub Actions Integration

The `.github/workflows/alchitry-ci-docker.yml` workflow uses the same test script as local development, ensuring consistency between local and CI environments.

## Troubleshooting

If Alchitry Labs commands fail:
1. Check that `$ALCHITRY_BIN` is set correctly in the container
2. Verify Java 22 is installed: `java -version`
3. Check Alchitry Labs installation: `find /root/alchitry-labs -name alchitry`