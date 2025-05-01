{ ocamlPackages
, nix-gitignore}:
ocamlPackages.buildDunePackage {
  useDune2 = true;

  pname = "taintfront";
  version = "0.1.0";

  src = nix-gitignore.gitignoreSource [] ../../taint-front;

  nativeBuildInputs = [
    ocamlPackages.menhir
  ];
}
