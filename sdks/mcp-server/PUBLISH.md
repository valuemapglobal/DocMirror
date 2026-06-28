# Publishing @docmirror/mcp-server to npm

This guide describes how to publish the MCP server npm package.

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

## Publish

### Via CI (recommended)

The `.github/workflows/publish-sdks.yml` workflow publishes on release tags.
Simply create a GitHub release with a tag like `mcp-server/v0.1.0`.

### Manually

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

## Post-Publish Checklist

- [ ] Verify: `npm view @docmirror/mcp-server`
- [ ] Verify: `npx @docmirror/mcp-server --help`
- [ ] Update README.md with any new features
- [ ] Tag the release: `git tag mcp-server/v0.1.0`
