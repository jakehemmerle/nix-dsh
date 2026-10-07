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
        web-boot =
          pkgs.runCommand "dsh-web-boot" { nativeBuildInputs = [ self.packages.${pkgs.stdenv.hostPlatform.system}.dsh ]; }
            ''
              export HOME=$(mktemp -d) DSH_HOME=$(mktemp -d)
              dsh web --no-open --port 0 > boot.log 2>&1 &
              pid=$!
              for _ in $(seq 120); do
                if grep -q 'http://127.0.0.1:' boot.log; then
                  kill $pid
                  touch $out
                  exit 0
                fi
                kill -0 $pid 2>/dev/null || break
                sleep 0.5
              done
              cat boot.log
              exit 1
            '';
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
