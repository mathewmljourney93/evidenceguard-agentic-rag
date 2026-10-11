# ADR-0001: One distribution, prefixed packages, nested layout

- **Status:** Accepted (plan decision D1), implemented in M1a
- **Date:** 2026-10-11

## Context

The approved repository structure groups code by role (`apps/api`, `apps/worker`, `packages/domain`, …). The code still has to import and install cleanly, without `sys.path` patches or `PYTHONPATH` workarounds. Short names such as `domain` or `agents` could also collide with other installed packages.

## Decision

- **One distribution.** A single `pyproject.toml` builds one distribution, `evidenceguard`, with Hatchling. Version, dependencies and release are managed in one place. Multiple distributions would add coordination without solving a current problem.
- **Prefixed import packages.** Every import package is named `evidenceguard_<role>`, for example `evidenceguard_api` and `evidenceguard_domain`. This avoids collisions with packages such as `agents`.
- **Nested layout.** Each package sits under its approved directory (`apps/api/evidenceguard_api/`, `packages/domain/evidenceguard_domain/`). Hatchling's `packages` option installs it at the top level of the wheel:

  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["apps/api/evidenceguard_api", "packages/domain/evidenceguard_domain"]
  ```

  An editable install (`uv sync`) adds plain path entries for `apps/api` and `packages/domain`, which Mypy and pytest both resolve.
- **Dependency direction.** `evidenceguard_domain` never imports application packages. A unit test checks this.
- **Only what is used.** A package directory is created in the milestone that first needs it. M1a has only the API and domain packages.

## Consequences

- Imports work the same from an editable checkout and from the built wheel. CI installs the wheel into a clean environment and imports it from outside the source tree.
- Adding a package means adding its path to the `packages` list (and to Mypy's `files` and Ruff's `known-first-party`).
- The directory names (`apps/api`) and import names (`evidenceguard_api`) differ, which is a small cost in readability.
