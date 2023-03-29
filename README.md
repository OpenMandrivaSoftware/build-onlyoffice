# Building OnlyOffice

This is (the beginning of) a script that will help build
OnlyOffice in a reasonable way, without half the operating
system its official build system bundles and builds.

Simply `cd` to the checkout directory and
run `./build.sh` to build.

It results in a `DesktopEditors` binary in
`desktop-apps/win-linux/build` as well as various libraries
all over the place. Set `LD_LIBRARY_PATH` to make sure
`DesktopEditors` can find all the libraries it needs
(or simply use `run.sh`).

# Current status

It compiles, and "works" if OnlyOffice is installed from
binary packages and then the binaries are overwritten with
the newly built binaries.

We currently don't have a way to build the remaining missing bits.

# CEF

Another big problem is the CEF blob. While CEF is theoretically Open Source,
it seems to be impossible to check out the source for older builds
(OnlyOffice requires build 4280) because apparently some branches
have been renamed and the build scripts hardcode the old names.
