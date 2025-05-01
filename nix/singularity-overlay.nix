self: super: {
  # Singularity without suid binaries for testing
  singularity = super.singularity.overrideAttrs (attrs: with attrs; {
    # Configures --without-suid
    postConfigure = ''
      cd go/src/github.com/sylabs/singularity

      patchShebangs .
      sed -i 's|defaultPath := "[^"]*"|defaultPath := "${super.lib.makeBinPath propagatedBuildInputs}"|' cmd/internal/cli/actions.go

      ./mconfig -V ${version} -p $out --localstatedir=/var --without-suid # added
    '';
    # Removes line:               #chmod 755 $out/libexec/singularity/bin/starter-suid
    installPhase = ''
      runHook preInstall
      make -C builddir install LOCALSTATEDIR=$out/var

      # Explicitly configure paths in the config file
      sed -i 's|^# mksquashfs path =.*$|mksquashfs path = ${super.lib.makeBinPath [self.squashfsTools]}/mksquashfs|' $out/etc/singularity/singularity.conf
      sed -i 's|^# cryptsetup path =.*$|cryptsetup path = ${super.lib.makeBinPath [self.cryptsetup]}/cryptsetup|' $out/etc/singularity/singularity.conf

      runHook postInstall
    '';

  });
}
