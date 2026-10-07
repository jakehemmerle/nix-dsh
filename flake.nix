{
  description = "DeepSeek Harness (dsh), packaged from npm and refreshed every 12 hours";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        dsh = pkgs.callPackage ./package.nix { };
        default = dsh;
      });

      overlays.default = final: _prev: { dsh = final.callPackage ./package.nix { }; };

      checks = forAllSystems (pkgs: {
        dsh = self.packages.${pkgs.stdenv.hostPlatform.system}.dsh;
        updater =
          pkgs.runCommand "dsh-updater-tests" { nativeBuildInputs = [ pkgs.python3 ]; }
            ''
              cp ${./update.py} update.py
              cp ${./test_update.py} test_update.py
              python3 -B -m unittest -v test_update
              touch $out
            '';
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.nodejs
            pkgs.python3
          ];
        };
      });
    };
}
