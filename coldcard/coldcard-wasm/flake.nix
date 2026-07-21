{
  description = "cmd/coldcard-wasm — pinned Emscripten + Python tooling for the Coldcard WebAssembly simulator.";

  # AD-2 (plan-coldcard-wasm-frame-2026-05-16.md):
  #   Emscripten 4.0.x default; fall back to 3.1.74 if the smoke build
  #   fails. The default below pins emscripten 4.x and emscriptenPackages.
  #   If you need 3.1.74, override at flake check / set EMSCRIPTEN_REV in
  #   cmd/coldcard-wasm/setup.sh and use the emsdk path instead of nix.
  #
  # This flake is provided for nix users; the setup.sh + build.sh
  # combination is the canonical build path and does not require nix.

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            emscripten
            python3
            python3Packages.pip
            gnumake
            git
            nodejs_20
          ];
          shellHook = ''
            echo "cmd/coldcard-wasm dev shell"
            echo "  emcc:    $(emcc --version | head -1)"
            echo "  python:  $(python3 --version)"
            echo "  node:    $(node --version)"
          '';
        };
      });
}
