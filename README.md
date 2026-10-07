# nix-dsh

Nix flake for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`), built from the `@deepseek-ai/dsh` npm release for `x86_64-linux`, `aarch64-linux` and `aarch64-darwin`.

```sh
nix run github:jakehemmerle/nix-dsh -- --version
```

As a flake input, use `packages.<system>.dsh` or `overlays.default`.

## Updates

`.github/workflows/update.yml` runs every 12 hours. It packages npm's `latest` dist-tag and ignores `alpha` and `next`. A new version reaches `main` only after `nix flake check` passes on Linux and macOS.

After a push, the workflow sends a `dsh-updated` `repository_dispatch` to `jakehemmerle/nix-config`. That step needs the `NIX_CONFIG_DISPATCH_TOKEN` secret, a fine-grained token with Contents read and write access to `nix-config` only. Without the secret it logs a warning and `nix-config` picks the update up on its own 12-hour schedule.

The current token is `nix-dsh to nix-config dispatch` (github.com/settings/personal-access-tokens/20753683). It expires on 2027-10-07. Regenerate it on that page and update the secret with `gh secret set NIX_CONFIG_DISPATCH_TOKEN -R jakehemmerle/nix-dsh`.

Every run ends with `update.py --check-freshness`. It fails when npm's `latest` has gone unpackaged for more than 48 hours.

Run an update locally with `nix develop -c python3 update.py`.

## Credits

`package.nix` is adapted from [numtide/llm-agents.nix](https://github.com/numtide/llm-agents.nix/blob/main/packages/dsh/package.nix) (MIT), including its `/bin/bash` fix. Unlike numtide's, dsh here runs on the official Node.js binary (`node.nix`), because `dsh web` fails on nixpkgs' nodejs with `Unsupported/no-getter`.
