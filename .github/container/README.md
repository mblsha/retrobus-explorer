# Alchitry CI Container

This directory contains a containerized version of the Alchitry CI environment that mirrors the GitHub Actions setup for local testing.

## Features

- Ubuntu 22.04 base image (matching GitHub Actions)
- Java 17 (OpenJDK) for Alchitry Labs
- Alchitry Labs V2 pre-installed
- Automated project syntax checking and test bench execution

## Requirements

- Apple Container runtime (`container` command) installed
- x86-64 emulation support (Rosetta 2 on Apple Silicon)

## Quick Start

1. Build the container:
   ```bash
   ./.github/container/build.sh
   ```

2. Test all projects:
   ```bash
   ./.github/container/test.sh
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

The container runs on `linux/amd64` platform because Alchitry Labs is distributed as an x86-64 binary. On Apple Silicon Macs, this requires Rosetta 2 emulation, which may impact performance.

## Files

- `Dockerfile` - Container definition with Java 17 and Alchitry Labs
- `build.sh` - Script to build the container image
- `test.sh` - Script to run CI checks locally
- `README.md` - This documentation

## Troubleshooting

If the build fails with architecture errors, ensure:
1. Rosetta 2 is installed on Apple Silicon
2. The `--platform linux/amd64` flag is used when building and running

If Alchitry Labs commands fail:
1. Check that `$ALCHITRY_BIN` is set correctly in the container
2. Verify Java 17 is installed: `java -version`
3. Check Alchitry Labs installation: `find /root/alchitry-labs -name alchitry`