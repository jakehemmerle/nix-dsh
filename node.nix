# dsh's node-addon-require-builtin locates a V8 getter by matching machine code
# from the official Node.js builds. nixpkgs' nodejs is compiled differently and
# fails `dsh web` with `Unsupported/no-getter`, so dsh runs on the official binary.
{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
}:

let
  version = "24.21.0";
  platforms = {
    aarch64-darwin = {
      name = "darwin-arm64";
      hash = "sha256-YjnUz5LYZEh+yM02FQOPe2fn9Yt3shzS8J6p+9aAZf4=";
    };
    x86_64-linux = {
      name = "linux-x64";
      hash = "sha256-/Y5Z1aURUQ9qKYr7VI8Yx9KxvkBNi0on2U++SfVsstY=";
    };
    aarch64-linux = {
      name = "linux-arm64";
      hash = "sha256-atEyXtvbVknDebdaI3FHpmbJXU+a6NNA/vLRV10omtI=";
    };
  };
  platform =
    platforms.${stdenv.hostPlatform.system}
      or (throw "official Node.js ${version} has no build for ${stdenv.hostPlatform.system}");
in
stdenv.mkDerivation {
  pname = "nodejs-official";
  inherit version;

  src = fetchurl {
    url = "https://nodejs.org/dist/v${version}/node-v${version}-${platform.name}.tar.xz";
    inherit (platform) hash;
  };

  nativeBuildInputs = lib.optional stdenv.hostPlatform.isLinux autoPatchelfHook;
  buildInputs = lib.optional stdenv.hostPlatform.isLinux stdenv.cc.cc.lib;

  dontConfigure = true;
  dontBuild = true;
  dontStrip = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -R bin include lib share $out/
    runHook postInstall
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    [ "$($out/bin/node --version)" = "v${version}" ]
  '';

  meta = {
    description = "Official Node.js release binary";
    homepage = "https://nodejs.org";
    license = lib.licenses.mit;
    mainProgram = "node";
    platforms = builtins.attrNames platforms;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
