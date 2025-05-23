{
  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
    nixpkgs-bleeding = {
      url = "github:NixOS/nixpkgs?ref=nixos-unstable";
    };
    jadx-plugin.url = "github:sandialabs/ctadl-jadx-fact-generator";
  };

  outputs = {
    self,
    nixpkgs,
    nixpkgs-bleeding,
    flake-utils,
    flake-compat,
    ...
  } @ inputs: let
    ctadlOverlay = final: prev: rec {
      soufflePackages = final.callPackage ./nix/souffle/packages.nix {};
      inherit (soufflePackages) souffle;

      jadxFactgenPackages = let
        scope = final.lib.fixedPoints.extends inputs.jadx-plugin.overlays.jadxFactgenOverlay (self: prev);
      in
        final.lib.makeScope final.newScope scope;

      taintfront = final.callPackage ./nix/taintfront/taintfront.nix {};

      ctadl-plugins = final.lib.recurseIntoAttrs (final.callPackage ./plugins.nix {
        jadxPlugin = final.jadxFactgenPackages.jadxFactgenPlugin;
      });

      ctadl-jadx = final.ctadl.withPlugins (with final.ctadl-plugins; [jadx]);

      ctadl-ghidra = final.ctadl.withPlugins (with final.ctadl-plugins; [ghidra]);

      ctadl-full = final.ctadl.withPlugins (with final.ctadl-plugins; [jadx ghidra final.ctadl-plugins.taintfront final.ctadl-plugins.networkxExport]);

      ctadl = final.callPackage ./ctadl.nix {};

      indexers-bin = final.callPackage ./indexers.nix {};

      # This needs to be in the overlay so other packages can call it properly.
      withPythonWheel = final: prev: {
        # We make a wheel output so that we can upload wheels to our gitlab
        # package registry, which makes it possible to pip install this package!
        # Note: it *cannot* be named "wheel" so we choose "whl". Apparently
        # building a python package can override that env var during
        # postInstall, making it point to the .whl file itself instead of the
        # nix dir to put the wheel in. Crazy stuff. The effect is that nix
        # expects an output named "wheel" but our postinstall script doesn't
        # work. Somehow this happens when this overlay is called from another
        # package but not when it's used in this package.
        outputs = prev.outputs ++ [ "whl" ];
        postInstall = prev.postInstall or ""
        + ''
          mkdir $whl
          cp dist/*.whl $whl/
        '';
      };
    };
  in
    {overlays = {inherit ctadlOverlay;};}
    // (
      flake-utils.lib.eachDefaultSystem (system: let
        pkgs = import nixpkgs {
          overlays = [
            (import ./nix/singularity-overlay.nix)
            (import ./nix/no-kvm-overlay.nix)
          ];
          inherit system;
        };
        python3 = pkgs.python39;

        # Need a newer nixpkgs for a few things
        bleeding = import nixpkgs-bleeding {inherit system;};
        checksarif =
          # Use x86_64 version on aarch because aarch version doesn't work
          (import nixpkgs-bleeding {
            system =
              if system == "aarch64-darwin"
              then "x86_64-darwin"
              else system;
          })
          .callPackage
          ./nix/sarif-multitool/checksarif.nix {
          };
        llvmPackages = pkgs.llvmPackages_10;
        soufflePackages = pkgs.callPackage ./nix/souffle/packages.nix {};
        ctadlPackages = let
          scope = pkgs.lib.fixedPoints.extends ctadlOverlay (self: {
            # Ensure to override python with current version in dependencies
            inherit python3;
            inherit (pkgs) lib stdenv;
            inherit llvmPackages;
          });
        in
          pkgs.lib.makeScope pkgs.newScope scope;

        inherit (ctadlPackages) taintfront;
        bundle = pkgs.symlinkJoin {
          name = "bundle";
          paths =
            [soufflePackages.souffle ctadlPackages.ctadl-full]
            ++ (with pkgs; [
              mcpp
              bash
              coreutils
              binutils
            ]);
          program = pkgs.writeShellScript "run-ctadl" ''
            # Souffle calls popen().
            # popen() tries to exec /bin/sh to run the commands you ask of it.
            # /bin/sh doesn't exist by default and this is how I put it in there.
            ${pkgs.coreutils}/bin/mkdir /bin
            ${pkgs.coreutils}/bin/ln -s ${pkgs.bash}/bin/sh /bin/sh
            exec ctadl "$@"
          '';
        };
        nginx-llvm = pkgs.callPackage ./nix/nginx/nginx-wllvm.nix {inherit llvmPackages;};
        nginx-debug = pkgs.callPackage ./nix/nginx/nginx.nix {};

        # python env to dev ctadl, does NOT contain ctadl
        std-packages = with pkgs;
          [
            mcpp
          ]
          ++ pkgs.lib.optionals pkgs.stdenv.isLinux (with pkgs; [glibcLocales glibc]);

        dockerImage = import "${self}/nix/docker.nix" {
          name = "ctadl";
          tag = "v${ctadlPackages.ctadl-full.version}";
          inherit self pkgs system;
          ctadl = ctadlPackages.ctadl-full;
          deps = [pkgs.bash pkgs.coreutils pkgs.binutils pkgs.less pkgs.more pkgs.jdk] ++ std-packages ++ [soufflePackages.souffle];
        };

        singularityImage = pkgs.callPackage ./nix/singularity.nix {
          name = "ctadl-full-v${ctadlPackages.ctadl-full.version}";
          ctadl = ctadlPackages.ctadl-full;
          inherit (soufflePackages) souffle;
          additionalDeps = std-packages ++ [];
        };

        ctadl-tests = let
          packages = [
            pkgs.stdenv.cc
            soufflePackages.souffle
            (python3.withPackages (ps: with ps; [ctadlPackages.ctadl-full ps.black]))
            checksarif
            pkgs.jdk
            pkgs.jq
            taintfront
            bleeding.pyright
            pkgs.gawk
            pkgs.gnused
          ];
        in
          pkgs.stdenv.mkDerivation {
            name = "ctadl-tests";
            version = "0.1.0";
            srcs = ./tests;
            nativeBuildInputs = [pkgs.makeWrapper python3.pkgs.wrapPython];
            installPhase = ''
              mkdir -p $out/bin
              cp ./bin/* $out/bin
              wrapProgram $out/bin/test \
                --prefix PATH ':' "${pkgs.lib.makeBinPath packages}" \
                --set JAVA_HOME "${pkgs.jdk.home}" \
                --set XDG_DATA_HOME "${ctadlPackages.indexers-bin}"
              wrapPythonPrograms
            '';
          };
        cctadl = pkgs.writeShellScriptBin "cctadl" ''
          export PYTHONPATH=
          ctadl_path=$( cd $(git rev-parse --show-toplevel) ; nix build .#ctadl-full --print-out-paths --no-link --offline )
          exec "$ctadl_path/bin/ctadl" "$@"
        '';

        release-script = pkgs.writeShellApplication {
          name = "make_images";
          runtimeInputs = with pkgs; [crane jq curl];
          text = builtins.readFile ./.release_scripts/make_images;
        };
      in {
        # remember nix run --system x86_64-darwin .#souffle23
        packages =
          {
            inherit soufflePackages ctadlPackages;
            inherit (soufflePackages) souffle;
            inherit (ctadlPackages) ctadl ctadl-full ctadl-jadx ;
            inherit (pkgs) jq; # used by cicd
            inherit (bleeding) pyright;
            inherit bundle python3 taintfront checksarif ctadl-tests nginx-debug;
            inherit nginx-llvm;
            docker = dockerImage;
          }
          // (pkgs.lib.optionalAttrs pkgs.stdenv.isLinux
            {singularity = singularityImage;});
        apps.test = {
          type = "app";
          program = "${ctadl-tests}/bin/test";
        };
        apps.release = {
          type = "app";
          program = "${release-script}/bin/make_images";
        };
        defaultPackage = ctadlPackages.ctadl;
        formatter = pkgs.alejandra;
        devShells.default = pkgs.mkShell {
          inputsFrom = [ctadlPackages.ctadl-full];
          packages = let
            pydev = python3.withPackages (ps: [
              ps.rich
              ps.black
              ps.isort
              ps.jsonschema
              ps.psutil
              ps.pyjson5
              ps.sphinx
              ps.sphinx-argparse
              ctadlPackages.ctadl-plugins.taintfront
              ctadlPackages.ctadl-plugins.jadx
              ctadlPackages.ctadl-plugins.ghidra
              ctadlPackages.ctadl-plugins.networkxExport
            ]);
          in [
            cctadl
            pydev
            soufflePackages.souffle
            pkgs.gdb
            bleeding.nodePackages.pyright
            bleeding.sqlite-interactive
            llvmPackages.llvm
            pkgs.ctags
            pkgs.jq
            pkgs.litecli
            pkgs.mcpp
            bleeding.pandoc
            self.packages.${system}.taintfront
            checksarif
          ];
          hardeningDisable = ["all"];
          shellHook = ''
            export GHIDRA_HOME="${pkgs.ghidra}/lib/ghidra"
            export JAVA_HOME="${pkgs.jdk.home}"
            # Lets us run ctadl from the current dev source tree
            export PYTHONPATH=`pwd`/src
            export PATH=$PATH:`pwd`/bin
          '';
        };
      })
    );
}
