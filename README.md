= Building OnlyOffice =

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

= Current status =

It compiles, but doesn't work -- crashes on startup.
