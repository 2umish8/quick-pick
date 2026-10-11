# Quick Pick — Maintenance constitution

## Context

`2umish8/quick-pick` is a public project under the MIT license. It has a single maintainer, who delegates development to AI agents and also runs a personal instance.

The goal is to keep the product installable, reliable and self-hostable, without mixing private data, local configuration and public code, and without creating an excessive maintenance burden.

## Non-negotiable rules

1. **Data separation.** No secret, token, real `.env` file, personal data, user history or local database is ever committed. Check tracked files, the diff and leak risks before anything is published.
2. **Separation of needs.** Explicitly distinguish the needs of the personal instance from the general needs of the product. When a need is personal, prefer local configuration over changing default behaviour.
3. **Repository integrity.** Work on dedicated branches. Every functional change must be reviewable through a pull request with tests and a rationale. Never merge, publish a release or push directly to `main` without explicit approval.
4. **Data protection.** Any change to storage must preserve existing data. Provide explicit, tested and documented migrations. Never reset or overwrite real data to work around a development problem.
5. **Compatibility.** Assume self-hosted installs may be several versions behind. Avoid silent breaking changes. Document incompatibilities, migration prerequisites and rollback options.
6. **Releases.** Merged code is not a published version. Every release needs an explicit tag, passing checks, release notes and an appropriate upgrade procedure.
7. **Verification.** Before a change, inspect the architecture, conventions and side effects. After it, check the diff, tests, security, compatibility and possible regressions. Never claim a check was done if it was not.

## Maintenance policy

- The maintainer alone decides the direction and priorities.
- Issues, feature requests and pull requests carry no commitment on timing.
- Contributions may be declined or closed if they are out of scope, risky or too costly to maintain.
- There is no obligation to answer every request.
- Credible security reports follow a private handling procedure.
- Automation and workflows must reduce real work, not create disproportionate administrative overhead.

## Guiding principle

Never sacrifice security, data integrity or maintainability for a local request, an external contribution or the urge to move fast.

Preserve the maintainer's ability to keep the project going at their own pace. The software's longevity comes before the number of features and the volume of contributions.
