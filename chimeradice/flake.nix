{
  description = "ChimeraDice development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pkgs.python311
            pkgs.uv
          ];

          shellHook = ''
            echo "ChimeraDice dev environment"
            echo "Python: $(python --version)"
            echo "uv: $(uv --version)"
            echo ""
            echo "Run: uv sync"
            echo "Test: uv run python -m unittest tests/test_chimeradice_properties.py -v"
          '';
        };
      }
    );
}
