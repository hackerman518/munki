# munkibuilds.org CI

This README is mainly useful for understanding of how the automated build system works, and to orient anyone interested in making changes to it.

## Overview

A Munki installer package is built for any branch pushed to this repo, and is published to a package listing available at https://munkibuilds.org. This process runs on a macOS worker VM via GitHub Actions.

100% of the package-building logic is already performed by `code/tools/make_munki_mpkg.sh`, and is wrapped in a Python-based build script at `code/tools/ci/build`. 

The "deploy" process is very simple: it simply copies several files to a remote server via rsync, and if the build was done on the master branch, it also symlinks a top-level to a stable "munkitools-latest" URL. These are useful for [Munki AutoPkg recipes](https://github.com/autopkg/recipes/tree/master/munkitools), for example. The SSH private key used to rsync files to the remote server is exposed via a secret stored in the repo's configuration.

It will also run this build process for any pull requests to the Munki repo, however pull requests from forks will not publish. For security reasons, forked repos do not have access to any secrets.

## Requirements

Currently tested on macOS 10.14, with Xcode 10.3, using Apple's system Python installation.

### textile

The build script requires one third-party Python package, `textile`, in order for the build descriptive text (git commit info, component info, etc.) to be displayed properly.

It's not strictly required: the script should handle it not being there and warn appropriately. For local testing or making changes to the build script(s), this can be skipped.

The recommended steps to install `textile` would be to set up a dedicated virtualenv using `virtualenv` or some tooling of your choice, and then install it using `pip install -r code/tools/ci/requirements.txt`.

`textile` is used as it greatly simplifies the process of rendering HTML from the templated "content" pages which are generated from commit logs, etc.


## Usage

To test the build script locally, simply run the build script from a Git checkout of the Munki source code. There may be assumptions about running at the root of the repo, so do run the script with your current working directory set to the root.

**Note about sudo:** `sudo` is not used here, however `make_munki_mpkg.sh` will eventually need `sudo` for packaging tasks. You don't have passwordless sudo on your own workstation, but you should be able to enter your password interactively when the build script is called. In the CI environment, passwordless sudo is available and we can rely on `make_munki_mpkg.sh` invoking `sudo` as needed.


```bash
cd ~/munki # your Munki Git checkout
git checkout <branch you want>
code/tools/ci/build
```

With no options, the build script will perform the build and store any artifacts in the `./artifacts` dir.

If an additional `--deploy-ssh-id-file` option is given, it will also perform a deploy step using the provided SSH identity file:

```bash
code/tools/ci/build --deploy-ssh-id-file /path/to/identity/file
```

## Additional notes

### Versioning

Currently, Munki component packages versions include a build number that is derived from the number of Git commits within that component's directory in the source tree. This means that versions aren't incremented if something changes outside the scope of that component.

If a change is made to a path in `tools` this won't bump the build version. However, this is infrequent and almost always due to tweaks in the package build scripts, presumably to fix an issue. For this reason, if a version is built that has been already published, it will overwrite it.

### sudo

The build machines used to run this have passwordless sudo available, so it calls the build script without `sudo`, since `make_munki_mpkg.sh` will already invoke `sudo` as needed. You may also call it this way an interactively add your password, which may make it simpler to clean up any staged artifacts.


### munkibuilds.org webserver configuration

This is currently served via a third-party VM hosted elsewhere. All of the functionality is provided by Apache and a collection of hacks around fancy directory listings. That configuration lives at https://github.com/timsutton/munkibuilds.org.

An [hourly cron](https://github.com/timsutton/munkibuilds.org/tree/master/prune_branches) on the server removes any subdirectories within the `_branches` directory if that branch no longer exists on the remote.

Someday this could be migrated to S3 or similar.
