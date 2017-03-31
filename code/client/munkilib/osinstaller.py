# encoding: utf-8
#
# Copyright 2017 Greg Neagle.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
osinstaller.py

Created by Greg Neagle on 2017-03-29.

Support for using startosinstall to install macOS.
"""

# stdlib imports
import os
import plistlib
import signal
import subprocess
import time
from xml.parsers.expat import ExpatError

# our imports
from . import display
from . import dmgutils
from . import munkilog
from . import munkistatus
from . import osutils
from . import pkgutils


class StartOSInstallError(Exception):
    '''Exception to raise if starting the macOS install fails'''
    pass


class StartOSInstallRunner(object):
    '''Handles running startosinstall to set up and kick off an upgrade install
    of macOS'''
    def __init__(self):
        self.dmg_mountpoint = None

    def sigusr1_handler(self, dummy_signum, dummy_frame):
        '''Signal handler for SIGUSR1 from startosinstall, which tells us it's
        done setting up the macOS install and is ready and waiting to reboot'''
        display.display_info('Got SIGUSR1 from startosinstall')
        # do stuff here: cleanup, record-keeping, notifications
        time.sleep(1)
        # then tell startosinstall it's OK to proceed with restart
        # can't use os.kill now that we wrap the call of startosinstall
        #os.kill(self.startosinstall_pid, signal.SIGUSR1)
        # so just target processes named 'startosinstall'
        subprocess.call(['/usr/bin/killall', '-SIGUSR1', 'startosinstall'])

    def get_tool_paths(self, dmgpath):
        '''Mounts dmgpath and returns paths to the Install macOS.app and
        startosinstall tool'''
        if pkgutils.hasValidDiskImageExt(dmgpath):
            display.display_info("Mounting disk image %s" % dmgpath)
            mountpoints = dmgutils.mountdmg(dmgpath)
            if mountpoints:
                self.dmg_mountpoint = mountpoints[0]
                # look in the first mountpoint for apps
                for item in osutils.listdir(self.dmg_mountpoint):
                    item_path = os.path.join(self.dmg_mountpoint, item)
                    startosinstall_path = os.path.join(
                        item_path, 'Contents/Resources/startosinstall')
                    if os.path.exists(startosinstall_path):
                        return (item_path, startosinstall_path)
                # if we get here we didn't find an Install macOS.app with the
                # expected contents
                dmgutils.unmountdmg(dmgpath)
                self.dmg_mountpoint = None
                raise StartOSInstallError(
                    'Valid Install macOS.app not found on %s' % dmgpath)
            else:
                raise StartOSInstallError(
                    u'No filesystems mounted from %s' % dmgpath)
        else:
            raise StartOSInstallError(
                u'%s doesn\'t appear to be a disk image' % dmgpath)

    def get_os_version(self, app_path):
        '''Returns the os version from the OS Installer'''
        installinfo_plist = os.path.join(
            app_path, 'Contents/SharedSupport/InstallInfo.plist')
        if not os.path.isfile(installinfo_plist):
            return ''
        try:
            info = plistlib.readPlist(installinfo_plist)
            return info['System Image Info']['version']
        except (ExpatError, IOError, KeyError, AttributeError, TypeError), err:
            return ''

    def start(self, dmgpath):
        '''Starts a macOS install from an Install macOS.app stored at the root
        of a disk image. Will always reboot after if the setup is successful.
        Therefore this must be done at the end of all other actions that Munki
        performs during a managedsoftwareupdate run.'''

        # set up our signal handler
        signal.signal(signal.SIGUSR1, self.sigusr1_handler)

        # get our tool paths
        install_app_path, startosinstall_path = self.get_tool_paths(dmgpath)

        os_version = self.get_os_version(install_app_path)

        display.display_status_major(
            'Starting macOS %s install...' % os_version)

        # run startosinstall via subprocess

        # we need to wrap our call to startosinstall with a utility
        # that makes startosinstall think it is connected to a tty-like
        # device so its output is unbuffered so we can get progress info
        # otherwise we get nothing until the process exits.
        #
        # Try to find our ptyexec tool
        # first look in the parent directory of this file's directory
        # (../)
        parent_dir = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)))
        ptyexec_path = os.path.join(parent_dir, 'ptyexec')
        if not os.path.exists(ptyexec_path):
            # try absolute path in munki's normal install dir
            ptyexec_path = '/usr/local/munki/ptyexec'
        if os.path.exists(ptyexec_path):
            cmd = [ptyexec_path]
        else:
            # fall back to /usr/bin/script
            # this is not preferred because it uses way too much CPU
            # checking stdin for input that will never come...
            cmd = ['/usr/bin/script', '-q', '-t', '1', '/dev/null']

        cmd.extend([startosinstall_path,
                    '--agreetolicense',
                    '--applicationpath', install_app_path,
                    '--rebootdelay', '300',
                    '--pidtosignal', str(os.getpid()),
                    '--nointeraction'])

        if pkgutils.MunkiLooseVersion(
                os_version) < pkgutils.MunkiLooseVersion('10.12.4'):
            # --volume option is _required_ prior to 10.12.4 installer
            # and must _not_ be included in 10.12.4 installer's startosinstall
            cmd.extend(['--volume', '/'])

        # more magic to get startosinstall to not buffer its output for
        # percent complete
        env = {'NSUnbufferedIO': ',YES'}

        proc = subprocess.Popen(cmd, shell=False, bufsize=0,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=env)

        startosinstall_output = []
        timeout = 2 * 60 * 60
        inactive = 0
        while True:
            info_output = proc.stdout.readline()
            if not info_output:
                if proc.poll() is not None:
                    break
                else:
                    # no data, but we're still running
                    inactive += 1
                    if inactive >= timeout:
                        # no output for too long, kill the job
                        display.display_error(
                            "startosinstall timeout after %d seconds"
                            % timeout)
                        proc.kill()
                        break
                    # sleep a bit before checking for more output
                    time.sleep(1)
                    continue

            # we got non-empty output, reset inactive timer
            inactive = 0

            info_output = info_output.decode('UTF-8')
            # save all startosinstall output in case there is
            # an error so we can dump it to the log
            startosinstall_output.append(info_output)
            # we don't know what/how to parse yet, so just display everything
            msg = info_output.rstrip('\n')
            if msg.startswith('By using the agreetolicense option'):
                pass
            elif msg.startswith('If you do not agree,'):
                pass
            elif (msg.startswith('Preparing ') and
                  not msg.startswith('Preparing to run ')):
                try:
                    percent = int(float(msg[10:].rstrip().rstrip('.')))
                except ValueError:
                    percent = -1
                display.display_percent_done(percent, 100)
            else:
                display.display_status_minor(msg)

        # osinstaller exited
        retcode = proc.returncode
        if retcode:
            dmgutils.unmountdmg(self.dmg_mountpoint)
            # append stderr to our startosinstall_output
            if proc.stderr:
                startosinstall_output.extend(proc.stderr.read().splitlines())
            display.display_status_minor(
                "Starting macOS install failed with return code %s" % retcode)
            display.display_error("-"*78)
            for line in startosinstall_output:
                display.display_error(line.rstrip("\n"))
            display.display_error("-"*78)
            raise StartOSInstallError(
                'startosinstall failed with return code %s' % retcode)
        else:
            munkilog.log("macOS install successfully set up.")
            munkistatus.percent(100)


def startosinstall(dmgpath):
    '''Run startosinstall to set up an install of macOS, using a Install app
    located on the given disk image. Returns True if startosinstall completes
    successfully, False otherwise.'''
    try:
        StartOSInstallRunner().start(dmgpath)
        return True
    except StartOSInstallError, err:
        display.display_error(
            u'Error starting macOS install: %s', unicode(err))
        return False


if __name__ == '__main__':
    print 'This is a library of support tools for the Munki Suite.'
