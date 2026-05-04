# NostrRelay Architecture Runbook (Non-Umbrel Focus)

Last updated: 2026-05-04

## Purpose

This runbook documents architecture and operations for `satwise/nostrrelay`, with emphasis on non-Umbrel deployments.

Repository: `https://github.com/satwise/nostrrelay`

Organization: `https://github.com/satwise`

## Repository Role

This repo provides application/control-plane functionality (LNbits extension style architecture), including:

- relay management UI and APIs
- websocket/API routing for relay operations
- account/payment/auth workflows
- storage/limits/business logic in extension data model

This repo is not the core relay source of truth. Core relay protocol/runtime lives in:

- `https://github.com/satwise/nostr-rs-relay`

## Runtime Architecture

- FastAPI routers for HTTP and websocket endpoints
- LNbits extension integration (auth, db access, extension lifecycle)
- Background tasks for payment and state workflows
- Static frontend assets served from extension path
- Multi-tenant relay model keyed by `relay_id`

## Deployment Model (Non-Umbrel)

Typical targets:

- Pi5 Debian
- generic Docker hosts
- VM deployments

If deployed alongside `nostr-rs-relay`, pin the same relay image digest used by Umbrel packaging for parity.

## Release and Compatibility Contract

- Keep deployment manifests explicit about required LNbits and Python versions.
- For relay dependencies, document exact relay image tag and digest.
- State tested architectures (`linux/arm64`, `linux/amd64`) for each release.

## Support Boundaries

Handled here:

- app/UI/API behavior in this repository
- extension lifecycle behavior
- non-Umbrel deployment docs for this app

Handled in core relay repo:

- protocol-level relay behavior
- relay engine performance and storage internals

Handled in Umbrel packaging repo:

- app_proxy wiring and Umbrel app lifecycle integration

## Incident Response and Rollback

1. Roll back deployment config to last known good app image or commit.
2. If issue is relay-engine specific, re-pin relay image digest to previous good release.
3. Record incident cause and fixed target versions in release notes.

## Cross-Repo Architecture Links

- Core relay runbook:
  `https://github.com/satwise/nostr-rs-relay/blob/master/ARCHITECTURE-RUNBOOK.md`
- Umbrel packaging runbook:
  `https://github.com/satwise/umbrel-apps/blob/master/nostr-relay/ARCHITECTURE-RUNBOOK.md`
