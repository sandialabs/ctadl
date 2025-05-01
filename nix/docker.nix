{ self, name, tag, ctadl, pkgs, system, deps }:
let
  stdenv = pkgs.stdenv;
in
  pkgs.dockerTools.buildImage {
    inherit name tag;

    #fromImage = someBaseImage;
    fromImageName = null;
    fromImageTag = "latest";

    copyToRoot = pkgs.buildEnv {
      name = "image-root";
      paths = [ ctadl ] ++ deps
        ++ (with pkgs.dockerTools; [ usrBinEnv caCertificates fakeNss ]);
      pathsToLink = [ "/bin" ];
    };

    config = {
      Entrypoint = [ "/bin/ctadl" ];
      WorkingDir = "/var/empty";
      Volumes = {
        "/var" = { };
        "/data" = { };
        "/tmp" = { };
      };
    };

    diskSize = 2048;
    buildVMMemorySize = 8192;
  }
