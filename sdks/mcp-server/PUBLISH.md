# Publishing @docmirror/mcp-server to npm (Blocked)

The package is not published. The repository workflow is preview-only and
must not push to npm or create tags. This document is an operator checklist
for a future explicitly approved first release.

## Release Blockers

- Confirm ownership of the `@docmirror` npm scope.
- Complete provenance, token, and two-factor-authentication setup.
- Pass the local build and package-content smoke checks.
- Remove the preview warning only in the same reviewed release PR.
- Obtain explicit approval for the exact version and registry action.

## Prerequisites

- npm account with access to the `@docmirror` organization
- npm token configured as `NPM_TOKEN` in GitHub repository secrets

## Build

```bash
cd sdks/mcp-server
npm install
npm run build   # compiles TypeScript src/ → dist/
```

Verify the build output:

```bash
ls dist/
# Should include: cli.js, cli.d.ts, index.js, index.d.ts
```

## Test Locally

```bash
node dist/cli.js --help
```

## Future Manual Publish

Do not run this section until every release blocker above is closed.

```bash
cd sdks/mcp-server

# Bump version in package.json
# Update the "version" field

# Build
npm run build

# Publish
npm publish --access public
```

## Versioning

- **Patch** (0.1.0 → 0.1.1): Bug fixes, internal improvements
- **Minor** (0.1.0 → 0.2.0): New MCP tools or parameters
- **Major** (1.0.0): Breaking changes to tool signatures

## Future Post-Publish Checklist

- [ ] Verify: `npm view @docmirror/mcp-server`
- [ ] Verify: `npx @docmirror/mcp-server --help`
- [ ] Update README.md with any new features
- [ ] Create the approved package tag only after registry verification
