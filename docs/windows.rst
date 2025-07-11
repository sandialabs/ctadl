Windows
=======

Although you may have better luck using a Mac system or a Linux system
or VM (or WSL), we provide a release zip that contains a `Windows
souffle
binary <https://github.com/sandialabs/ctadl/releases/download/v0.11.0/souffle-windows-x64.zip>`__
There is a ``souffle.bat`` file in there that you use to run souffle.

* To run souffle directly (example outputting to stdout on a simple test):
  ``.\souffle-windows-x64\souffle.bat -D- .\souffle-windows-x64\test.dl``

* To run ctadl after installing:
  ``py -3 \path\to\ctadl\bin\ctadl --souffle .\path\to\souffle.bat ...`` -
  To run ctadl in the mode where souffle compiles binaries for the
  analysis, you first have to install Visual Studio, then run something
  like this in cmd.exe (although with additional effort you can run
  ``vcvars64.bat`` in powershell), substituting your paths:

.. code:: bat

   "C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat"
   set PATH=%PATH%;\path\to\souffle-windows-x64
   py -3 \path\to\ctadl\bin\ctadl --souffle souffle.bat index -f -C .\binary_name \path\to\facts
   .\binary_name.exe -F \path\to\facts

*  For the above, the souffle directory needs to be in your path so the
   library files are picked up since windows uses binary and load path
   as the same thing; you can also add it to the path in your system or
   user environment variables so you don’t have to do that every time.
   It’s also a similar process for queries.

*  You can do the Ghidra import in the Ghidra GUI as normal on Windows,
   but to run it in headless mode, do something like (in powershell):

.. code:: powershell

   # This has to be either set in the terminal, or in environment variables to the path to the outer ghidra directory
   $Env:GHIDRA_HOME = "C:\path\to\ghidra_XX.Y_PUBLIC"
   $pcode_facts_path = "\path\to\facts\output"
   mkdir $pcode_facts_path -ErrorAction SilentlyContinue
   $ctadl_path = "\path\to\ctadl"
   # first arg is project parent dir, "curl" is project name
   & $ctadl_path\src\ctadl\souffle-logic\pcode\analyzeHeadlessBigMem.bat $pcode_facts_path curl -import \path\to\binary -deleteProject -scriptPath $ctadl_path\src\ctadl\souffle-logic\pcode -postScript ExportPCodeForCTADL.java $pcode_facts_path

Building Souffle on Windows
---------------------------

If you'd like to build Souffle on Windows yourself:

-  Install visual studio with C++ desktop build stuff so you have the
   mscv compiler. If needed, apply license key with
   ``help -> register visual studio``.
-  Install vcpkg either by downloading as a zip or pulling from git:
   ``git clone https://github.com/microsoft/vcpkg.git && cd vcpkg && bootstrap-vcpkg.bat``

   -  You may have to unblock the following powershell scripts with
      ``right click -> properties -> unblock -> apply``:
      ``scripts\bootstrap.ps1``,
      ``scripts\buildsystems\msbuild\applocal.ps1``.
   -  Then, put vcpkg dir somewhere and add it to your path (vcpkg.exe,
      built from above, needs to know where the vcpkg dir is, so you
      can’t just call copy the .exe somewhere by itself).

-  Do the following steps in powershell, replacing Visual Studio version
   string as needed (and Visual Studio path for the tests part):

.. code:: powershell

   # run this in powershell to download chocolatey
   [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
   # choco-packages.config is in the root of the souffle source dir
   choco install choco-packages.config -y --no-progress --installargs 'ADD_CMAKE_TO_PATH=""System""'

   # in the souffle src dir, under powershell
   vcpkg new --application
   vcpkg add port sqlite3 zlib libffi
   # (dependencies will be installed in the build step, this is to do it manually): vcpkg install --triplet=x64-windows

   # build with cmake (under powershell, in souffle dir; Visual Studio 16 2019 32-bit and Visual Studio 17 2022 64-bit have both worked)
   mkdir build -ErrorAction SilentlyContinue
   $env:ChocolateyInstall = Convert-Path "$((Get-Command choco).Path)\..\.."
   Import-Module "$env:ChocolateyInstall\helpers\chocolateyProfile.psm1"
   refreshenv
   # this gets it from the exe in your path, but you can also just set VCPKG_ROOT manually to your vcpkg source directory
   $VCPKG_ROOT = (Get-Item (gcm vcpkg).Path).DirectoryName
   # Help -> About Microsoft Visual Studio
   $VS_VERSION = "Visual Studio 17 2022"
   # unblock vcpkg\scripts\buildsystems\msbuild\applocal.ps1 first (see above)
   # I got errors with cmake finding gzip.exe, choco install --force gzip to force reinstall it worked (it downloaded files but didn't run the install script for some reason)
   # -DCMAKE_BUILD_TYPE=Release
   cmake -S . -B build -G "${VS_VERSION}" -A x64 "-DCMAKE_TOOLCHAIN_FILE=${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS=/bigobj -DSOUFFLE_DOMAIN_64BIT=ON -DCMAKE_FIND_LIBRARY_PREFIXES=";lib" -DCMAKE_FIND_LIBRARY_SUFFIXES=".lib;.dll" -DSOUFFLE_USE_CURSES=OFF -DSOUFFLE_USE_ZLIB=ON -DCMAKE_FIND_DEBUG_MODE=FALSE -DSOUFFLE_BASH_COMPLETION=OFF
   $nthreads = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
   cmake --build build --config Release -j ${nthreads}
   # now, find the .exe in build\src\souffle.exe

   # If you want, you can figure out how to do static linking with cmake to make a standalone binary; shouldn't be necessary, you can just include all .dlls in the build dir (can get in visual studio dev prompt: dumpbin /dependents souffle.exe)

   # run tests (in souffle source dir build from above); replace visual studio path with your path
   # Visual Studio must be in the environment because cl.exe is required for compiled Souffle.
   & "$env:ProgramFiles\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
   ctest --output-on-failure --build-config Release --progress -j4 -L interpreted
   ctest --output-on-failure --build-config Release --progress -j2 -LE interpreted
