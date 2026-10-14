{
  lib,
  buildNpmPackage,
  fetchurl,
  jq,
  runCommand,
  nodejs,
  # Plugin contributions applied on top of the stock release, in list order.
  # Each element is what a plugin repo's `nix/tui-patch.nix` returns:
  #   { name; patches ? [ ]; postPatch ? ""; installCheck ? ""; }
  # `installCheck` runs after installation with DSH_TUI_TYPES (the installed
  # lib/types directory) and an empty HOME, so it tests the exact artifact.
  plugins ? [ ],
}:

# dsh-TUI (https://github.com/ccch1mneyyy/dsh-TUI), the community terminal
# front end for DeepSeek Harness. The npm tarball ships no lockfile; ours was
# generated with
#   npm install --package-lock-only --omit=dev --legacy-peer-deps --ignore-scripts
# against the manifest edited exactly as in `src` below. Peers are DSH's own
# packages, which the dsh Loader supplies at runtime, so they are not installed.
# To update: bump version and hash, regenerate dsh-tui/package-lock.json,
# recompute unlistedPeers (README), then fix npmDepsHash from the build error.
let
  version = "0.15.0";
  tarball = fetchurl {
    url = "https://registry.npmjs.org/@deepseek-harness-tui/dsh-tui/-/dsh-tui-${version}.tgz";
    hash = "sha512-nkqFRJX/dUp/+AQOqHaiTcvZ3YZd9Hme75ULwH4btN6yjGkeGhH2CKm33imJrs7wJ4LJxPGe77mgxfsNhM98/g==";
  };
  # DSH packages dsh-TUI imports without listing them as peers. dsh routes a
  # store-linked package's @deepseek-ai/* imports to its own copies only for
  # names listed there, so they are added as optional peers.
  unlistedPeers = [
    "@deepseek-ai/cordis-plugin-include"
    "@deepseek-ai/cordis-plugin-loader"
    "@deepseek-ai/dsh-agent-preset"
    "@deepseek-ai/dsh-attachment-local"
    "@deepseek-ai/dsh-base"
    "@deepseek-ai/dsh-mcp-client"
    "@deepseek-ai/dsh-session-persistence"
    "@deepseek-ai/dsh-session-persistence-jsonl"
  ];
  # npm ci empties node_modules, so the bundled @dsh-std and @dsh-tui-vendor
  # packages are moved aside and restored after installation.
  src = runCommand "dsh-tui-source-${version}" { nativeBuildInputs = [ jq ]; } ''
    mkdir -p $out
    tar -xzf ${tarball} -C $out --strip-components=1
    jq --argjson names '${builtins.toJSON unlistedPeers}' '
      .peerDependencies += ($names | map({ key: ., value: "*" }) | from_entries)
      | .peerDependenciesMeta += ($names | map({ key: ., value: { optional: true } }) | from_entries)' \
      $out/package.json > $out/package.json.runtime
    jq 'del(.devDependencies, .scripts, .bundledDependencies, .peerDependencies, .peerDependenciesMeta)
      | .optionalDependencies |= with_entries(select(.key | startswith("@dsh-") | not))' \
      $out/package.json.runtime > $out/package.json
    mv $out/node_modules $out/bundled
    cp ${./dsh-tui/package-lock.json} $out/package-lock.json
  '';
  pluginNames = map (p: p.name) plugins;
in
assert lib.assertMsg (lib.unique pluginNames == pluginNames) "dsh-tui: duplicate plugin contribution";
buildNpmPackage {
  pname = "dsh-tui";
  inherit version src nodejs;

  # preset-schedule-deny: DSH 0.2.1-alpha's Standard/PTC/Cordis presets deny
  # schedule_* to subagents, but those tools exist only beside dsh-web-app's
  # schedule service, which a TUI-only profile lacks; tools.restrict() then
  # rejects every subagent/subagent_fork call. Without that service the TUI's
  # copy of the presets drops exactly those names. Drop once
  # https://github.com/ccch1mneyyy/dsh-TUI/issues/1450 is fixed.
  patches = [ ./dsh-tui/preset-schedule-deny.patch ] ++ lib.concatMap (p: p.patches or [ ]) plugins;

  postPatch = lib.concatMapStrings (p: lib.optionalString ((p.postPatch or "") != "") ''
    echo "dsh-tui: postPatch from ${p.name}"
    ${p.postPatch}
  '') plugins;

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-FmzSN6s2dj85dUNB6Zgdd7xyR1ycFR56ss7MXAtNqJc=";
  npmFlags = [
    "--legacy-peer-deps"
    "--ignore-scripts"
  ];
  dontNpmBuild = true;

  postInstall = ''
    pkg=$out/lib/node_modules/@deepseek-harness-tui/dsh-tui
    cp -r bundled/. $pkg/node_modules/
    cp package.json.runtime $pkg/package.json
    # Its launchers bootstrap and self-update a mutable profile; a Nix profile
    # is immutable, so consumers provide their own launcher (dsh --profile).
    rm -r $out/bin
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    export DSH_TUI_TYPES=$out/lib/node_modules/@deepseek-harness-tui/dsh-tui/lib/types
    export HOME=$(mktemp -d)
    node --test ${./dsh-tui/test}/*.test.mjs
  '' + lib.concatMapStrings (p: lib.optionalString ((p.installCheck or "") != "") ''
    echo "dsh-tui: installCheck from ${p.name}"
    (export HOME=$(mktemp -d); ${p.installCheck})
  '') plugins + ''
    runHook postInstallCheck
  '';

  passthru = {
    inherit plugins;
    typesDir = "lib/node_modules/@deepseek-harness-tui/dsh-tui/lib/types";
    packageDir = "lib/node_modules/@deepseek-harness-tui/dsh-tui";
  };

  meta = {
    description = "Terminal user interface for DeepSeek Harness";
    homepage = "https://github.com/ccch1mneyyy/dsh-TUI";
    changelog = "https://github.com/ccch1mneyyy/dsh-TUI/releases/tag/v${version}";
    license = lib.licenses.mit;
    platforms = lib.platforms.all;
  };
}
