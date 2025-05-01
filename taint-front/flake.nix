{
  description = "Taint frontend flake";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    { } //
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        # fbinfer = pkgs.callPackage ./fbinfer.nix { };
      in
      {
        packages = {
          # inherit fbinfer;
          # inherit (mopsa) devShell ciShell;
          taint-front = pkgs.ocamlPackages.buildDunePackage {
            useDune2 = true;

            pname = "taint-front";
            version = "0.1.0";

            src = pkgs.nix-gitignore.gitignoreSource [] ./.;

            nativeBuildInputs = [
              pkgs.ocamlPackages.menhir
            ];
          };
          default = self.packages.${system}.taint-front;
        };
        devShell = pkgs.mkShell {
          inputsFrom = [  ];
          packages = with pkgs.ocamlPackages; [
            merlin odoc utop menhir ocamlbuild ocaml dune_2
          ];
          # inherit (fbinfer) configureFlags makeFlags preBuild;
        };
      });

}
