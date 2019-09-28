# munkibuilds.org CI

This README is mainly useful for understanding of how the automated build system works, and to orient anyone interested in making changes to it.

## Overview

A Munki installer package is built for any branch pushed to this repo, and is published to a package listing available at https://munkibuilds.org. This entire process runs on a macOS worker VM using [Azure DevOps Pipelines](https://azure.microsoft.com/en-us/services/devops/pipelines/). This effort has been migrated from a Jenkins-based build that has run [since 2012](https://groups.google.com/d/msg/munki-dev/keTd96IokyA/dwhXv3I0KLoJ), most of which is documented at https://github.com/timsutton/munkibuilds.org.

100% of the package-building logic is already performed by `code/tools/make_munki_mpkg.sh`, and is wrapped in a Python-based build script at `code/tools/ci/build`. 

The "deploy" process is very simple: it simply copies several files to a remote server via rsync, and optionally symlinks that build to a stable "munkitools-latest" URL if the build was done on the master branch.

It should also run this build process for any PRs but does not go through the publishing step so as to protect the credentials.

Currently all of the logic is contained within a single script located at `code/tools/ci/build`.

## Requirements

Currently tested on macOS 10.13 and 10.14, with at least Xcode 9.4.1, using Apple's system Python installation.

### textile

The build script requires one third-party Python package, `textile`, in order for the build descriptive text (git commit info, component info, etc.) to be displayed properly. It's not strictly required (the script should handle it not being there and warn appropriately), so for testing any other aspect of the build script locally (the build, staging files, etc.) this can be skipped.

The recommended steps to install `textile` would be to set up a dedicated virtualenv using `virtualenv` or some tooling of your choice, and then install it using `pip install -r code/tools/ci/requirements.txt`.

`textile` is used as it greatly simplifies the process of rendering HTML from the templated "content" pages which are generated from commit logs, etc.


## Usage

To test the build script locally, simply run the build script from a Git checkout of the Munki source code. There may be assumptions about running at the root of the repo, so do run the script with your current working directory set to the root.

```bash
cd ~/munki # your Munki Git checkout
git checkout <branch you want>
sudo code/tools/ci/build
```

With no options, the build script will perform the build and store any artifacts in the `./artifacts` dir.

If an additional `--deploy-ssh-id-file` option is given, it will also perform a deploy step using the provided SSH identity file:

```bash
sudo code/tools/ci/build --deploy-ssh-id-file /path/to/identity/file
```

## Versioning

Currently, Munki component packages versions include a build number that is derived from the number of Git commits within that component's directory in the source tree. This means that versions aren't incremented if something changes outside the scope of that component.

If a change is made to a path in `tools` this won't bump the build version. However, this is infrequent and almost always due to tweaks in the package build scripts, presumably to fix an issue. For this reason, if a version is built that has been already published, it will overwrite it.

## Azure configuration

### build phases

The build and publishing is performed entirely in the `build` script for simplicity's sake. There's no usage of the "releases" system in Azure, to avoid over-engineering for a solution that simply needs to publish automated builds.

### secrets

A single secret is currently used for publishing over SSH, which has been stored encrypted in the Azure project and which is copied to the runner early during the build process.

### sudo

The Azure build agents used to run this have passwordless sudo available, so it calls the build script without `sudo`, since `make_munki_mpkg.sh` will already invoke `sudo` as needed. You may also call it this way an interactively add your password, which may make it simpler to clean up any staged artifacts.


## munkibuilds.org webserver configuration

This is currently served via a third-party VM hosted elsewhere. All of the functionality is provided by Apache and a collection of hacks around fancy directory listings. That configuration lives at https://github.com/timsutton/munkibuilds.org.

An [hourly cron](https://github.com/timsutton/munkibuilds.org/tree/master/prune_branches) on the server removes any subdirectories within the `_branches` directory if that branch no longer exists on the remote.

Someday this could potentially be migrated to a something like S3.
