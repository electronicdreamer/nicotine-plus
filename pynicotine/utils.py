# COPYRIGHT (C) 2020-2021 Nicotine+ Team
# COPYRIGHT (C) 2020 Lene Preuss <lene.preuss@gmail.com>
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2007 Daelstorm <daelstorm@gmail.com>
# COPYRIGHT (C) 2003-2004 Hyriand <hyriand@thegraveyard.org>
# COPYRIGHT (C) 2001-2003 Alexander Kanavin
#
# GNU GENERAL PUBLIC LICENSE
#    Version 3, 29 June 2007
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This module contains utility functions.
"""

import errno
import os
import pickle

from pynicotine.config import config
from pynicotine.logfacility import log

ILLEGALPATHCHARS = ["?", ":", ">", "<", "|", "*", '"']
ILLEGALFILECHARS = ILLEGALPATHCHARS + ["\\", "/"]
REPLACEMENTCHAR = '_'


def rename_process(new_name, debug_info=False):

    errors = []

    # Renaming ourselves for pkill et al.
    try:
        import ctypes
        # GNU/Linux style
        libc = ctypes.CDLL(None)
        libc.prctl(15, new_name, 0, 0, 0)

    except Exception as error:
        errors.append(error)
        errors.append("Failed GNU/Linux style")

        try:
            import ctypes
            # BSD style
            libc = ctypes.CDLL(None)
            libc.setproctitle(new_name)

        except Exception as error:
            errors.append(error)
            errors.append("Failed BSD style")

    if debug_info and errors:
        msg = ["Errors occurred while trying to change process name:"]
        for i in errors:
            msg.append("%s" % (i,))
        print('\n'.join(msg))


def clean_file(filename):

    for char in ILLEGALFILECHARS:
        filename = filename.replace(char, REPLACEMENTCHAR)

    return filename


def clean_path(path, absolute=False):

    # Without hacks it is (up to Vista) not possible to have more
    # than 26 drives mounted, so we can assume a '[a-zA-Z]:\' prefix
    # for drives - we shouldn't escape that
    drive = ''
    if absolute and path[1:3] == ':\\' and path[0:1] and path[0].isalpha():
        drive = path[:3]
        path = path[3:]

    for char in ILLEGALPATHCHARS:
        path = path.replace(char, REPLACEMENTCHAR)

    path = ''.join([drive, path])

    # Path can never end with a period on Windows machines
    path = path.rstrip('.')

    return path


def get_path(folder_name, base_name, callback, data=None):
    """ Call a specified function, supplying an optimal file path depending on
    which path characters the target file system supports """

    try:
        filepath = os.path.join(folder_name, base_name)
        callback(filepath, data)

    except OSError as error:
        if error.errno != errno.EINVAL:
            # The issue is not caused by invalid path characters, raise error as usual
            raise OSError from error

        # Use path with forbidden characters removed (NTFS/FAT)
        filepath = os.path.join(folder_name, clean_file(base_name))
        callback(filepath, data)


def get_latest_version():

    import json

    response = http_request(
        "https", "pypi.org", "/pypi/nicotine-plus/json",
        headers={"User-Agent": "Nicotine+"}
    )
    data = json.loads(response)

    hlatest = data['info']['version']
    latest = int(make_version(hlatest))

    try:
        date = data['releases'][hlatest][0]['upload_time']
    except Exception:
        date = None

    return hlatest, latest, date


def make_version(version):

    major, minor, patch = (int(i) for i in version.split(".")[:3])
    stable = 1

    if "dev" in version or "rc" in version:
        # Example: 2.0.1.dev1
        # A dev version will be one less than a stable version
        stable = 0

    return (major << 24) + (minor << 16) + (patch << 8) + stable


def get_result_bitrate_length(filesize, attributes):
    """ Used to get the audio bitrate and length of search results and
    user browse files """

    h_bitrate = ""
    h_length = ""

    bitrate = 0
    length = 0

    # If there are 3 entries in the attribute list
    if len(attributes) == 3:

        first = attributes[0]
        second = attributes[1]
        third = attributes[2]

        # Sometimes the vbr indicator is in third position
        if third in (0, 1):

            if third == 1:
                h_bitrate = " (vbr)"

            bitrate = first
            h_bitrate = str(bitrate) + h_bitrate

            length = second
            h_length = '%i:%02i' % (second / 60, second % 60)

        # Sometimes the vbr indicator is in second position
        elif second in (0, 1):

            if second == 1:
                h_bitrate = " (vbr)"

            bitrate = first
            h_bitrate = str(bitrate) + h_bitrate

            length = third
            h_length = '%i:%02i' % (third / 60, third % 60)

        # Lossless audio, length is in first position
        elif third > 1:

            # Bitrate = sample rate (Hz) * word length (bits) * channel count
            # Bitrate = 44100 * 16 * 2
            bitrate = (second * third * 2) / 1000
            h_bitrate = str(bitrate)

            length = first
            h_length = '%i:%02i' % (first / 60, first % 60)

        else:

            bitrate = first
            h_bitrate = str(bitrate) + h_bitrate

    # If there are 2 entries in the attribute list
    elif len(attributes) == 2:

        first = attributes[0]
        second = attributes[1]

        # Sometimes the vbr indicator is in second position
        if second in (0, 1):

            # If it's a vbr file we can't deduce the length
            if second == 1:

                h_bitrate = " (vbr)"

                bitrate = first
                h_bitrate = str(bitrate) + h_bitrate

            # If it's a constant bitrate we can deduce the length
            else:

                bitrate = first
                h_bitrate = str(bitrate) + h_bitrate

                if bitrate <= 0:
                    length = 0
                else:
                    # Dividing the file size by the bitrate in Bytes should give us a good enough approximation
                    length = filesize / (bitrate / 8 * 1000)

                h_length = '%i:%02i' % (length / 60, length % 60)

        # Sometimes the bitrate is in first position and the length in second position
        else:

            bitrate = first
            h_bitrate = str(bitrate) + h_bitrate

            length = second
            h_length = '%i:%02i' % (second / 60, second % 60)

    return h_bitrate, bitrate, h_length, length


size_suffixes = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']


def human_size(filesize):
    try:
        step_unit = 1024.0

        for i in size_suffixes:
            if filesize < step_unit:
                return "%3.1f %s" % (filesize, i)

            filesize /= step_unit

    except TypeError:
        pass

    return filesize


speed_suffixes = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s', 'EiB/s', 'ZiB/s', 'YiB/s']


def human_speed(filesize):
    try:
        step_unit = 1024.0

        for i in speed_suffixes:
            if filesize < step_unit:
                return "%3.1f %s" % (filesize, i)

            filesize /= step_unit

    except TypeError:
        pass

    return filesize


def humanize(number):

    fashion = config.sections["ui"]["decimalsep"]

    if fashion in ("", "<None>"):
        return str(number)

    if fashion == "<space>":
        fashion = " "

    number = str(number)

    if number[0] == "-":
        neg = "-"
        number = number[1:]
    else:
        neg = ""

    ret = ""

    while number[-3:]:
        part, number = number[-3:], number[:-3]
        ret = "%s%s%s" % (part, fashion, ret)

    return neg + ret[:-1]


def unescape(string):
    """Removes quotes from the beginning and end of strings, and unescapes it."""

    string = string.encode('latin-1', 'backslashreplace').decode('unicode-escape')

    try:
        if (string[0] == string[-1]) and string.startswith(("'", '"')):
            return string[1:-1]
    except IndexError:
        pass

    return string


def execute_command(command, replacement=None, background=True, returnoutput=False, placeholder='$'):
    """Executes a string with commands, with partial support for bash-style quoting and pipes.

    The different parts of the command should be separated by spaces, a double
    quotation mark can be used to embed spaces in an argument.
    Pipes can be created using the bar symbol (|).

    If background is false the function will wait for all the launched
    processes to end before returning.

    If the 'replacement' argument is given, every occurance of 'placeholder'
    will be replaced by 'replacement'.

    If the command ends with the ampersand symbol background
    will be set to True. This should only be done by the request of the user,
    if you want background to be true set the function argument.

    The only expected error to be thrown is the RuntimeError in case something
    goes wrong while executing the command.

    Example commands:
    * "C:\\Program Files\\WinAmp\\WinAmp.exe" --xforce "--title=My Window Title"
    * mplayer $
    * echo $ | flite -t """

    from subprocess import PIPE
    from subprocess import Popen

    # Example command: "C:\Program Files\WinAmp\WinAmp.exe" --xforce "--title=My Title" $ | flite -t
    if returnoutput:
        background = False

    command = command.strip()

    if command.endswith("&"):
        command = command[:-1]
        if returnoutput:
            print("Yikes, I was asked to return output but I'm also asked to launch "
                  "the process in the background. returnoutput gets precedent.")
        else:
            background = True

    unparsed = command
    arguments = []

    while unparsed.count('"') > 1:

        (pre, argument, post) = unparsed.split('"', 2)
        if pre:
            arguments += pre.rstrip(' ').split(' ')

        arguments.append(argument)
        unparsed = post.lstrip(' ')

    if unparsed:
        arguments += unparsed.split(' ')

    # arguments is now: ['C:\Program Files\WinAmp\WinAmp.exe', '--xforce', '--title=My Title', '$', '|', 'flite', '-t']
    subcommands = []
    current = []

    for argument in arguments:
        if argument in ('|',):
            subcommands.append(current)
            current = []
        else:
            current.append(argument)

    subcommands.append(current)

    # subcommands is now: [['C:\Program Files\WinAmp\WinAmp.exe', '--xforce', '--title=My Title', '$'], ['flite', '-t']]
    if replacement:
        for i, _ in enumerate(subcommands):
            subcommands[i] = [x.replace(placeholder, replacement) for x in subcommands[i]]

    # Chaining commands...
    finalstdout = None
    if returnoutput:
        finalstdout = PIPE

    procs = []

    try:
        if len(subcommands) == 1:  # no need to fool around with pipes
            procs.append(Popen(subcommands[0], stdout=finalstdout))
        else:
            procs.append(Popen(subcommands[0], stdout=PIPE))
            for subcommand in subcommands[1:-1]:
                procs.append(Popen(subcommand, stdin=procs[-1].stdout, stdout=PIPE))
            procs.append(Popen(subcommands[-1], stdin=procs[-1].stdout, stdout=finalstdout))
        if not background and not returnoutput:
            procs[-1].wait()
    except Exception as error:
        raise RuntimeError("Problem while executing command %s (%s of %s)" %
                           (subcommands[len(procs)], len(procs) + 1, len(subcommands))) from error

    if not returnoutput:
        return True

    return procs[-1].communicate()[0]


def load_file(path, load_func, use_old_file=False):

    try:
        if use_old_file:
            path = path + ".old"

        elif os.path.isfile(path + ".old"):
            if not os.path.isfile(path):
                raise OSError("*.old file is present but main file is missing")

            if os.path.getsize(path) == 0:
                # Empty files should be considered broken/corrupted
                raise OSError("*.old file is present but main file is empty")

        return load_func(path)

    except Exception as error:
        log.add(_("Something went wrong while reading file %(filename)s: %(error)s"),
                {"filename": path, "error": error})

        if not use_old_file:
            # Attempt to load data from .old file
            log.add(_("Attempting to load backup of file %s"), path)
            return load_file(path, load_func, use_old_file=True)

    return None


def write_file_and_backup(path, callback, protect=False):

    # Back up old file to path.old
    try:
        if os.path.exists(path):
            from shutil import copy2
            copy2(path, path + ".old")

            if protect:
                os.chmod(path + ".old", 0o600)

    except Exception as error:
        log.add(_("Unable to back up file %(path)s: %(error)s"), {
            "path": path,
            "error": error
        })

    # Save new file
    if protect:
        oldumask = os.umask(0o077)

    try:
        with open(path, "w", encoding="utf-8") as file_handle:
            callback(file_handle)

    except Exception as error:
        log.add(_("Unable to save file %(path)s: %(error)s"), {
            "path": path,
            "error": error
        })

        # Attempt to restore file
        try:
            if os.path.exists(path + ".old"):
                os.rename(path + ".old", path)

        except Exception as error:
            log.add(_("Unable to restore previous file %(path)s: %(error)s"), {
                "path": path,
                "error": error
            })

    if protect:
        os.umask(oldumask)


def http_request(url_scheme, base_url, path, request_type="GET", body="", headers=None, timeout=10, redirect_depth=0):

    if headers is None:
        headers = {}

    import http.client

    if redirect_depth > 15:
        raise http.client.HTTPException("Redirected too many times, giving up")

    if url_scheme == "https":
        conn = http.client.HTTPSConnection(base_url, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(base_url, timeout=timeout)

    conn.request(request_type, path, body=body, headers=headers)
    response = conn.getresponse()
    redirect = response.getheader('Location')

    if redirect:
        from urllib.parse import urlparse
        parsed_url = urlparse(redirect)
        redirect_depth += 1

        return http_request(
            parsed_url.scheme, parsed_url.netloc, parsed_url.path,
            request_type, body, headers, timeout, redirect_depth
        )

    contents = response.read().decode("utf-8")
    conn.close()

    return contents


class RestrictedUnpickler(pickle.Unpickler):
    """
    Don't allow code execution from pickles
    """

    def find_class(self, module, name):
        # Forbid all globals
        raise pickle.UnpicklingError("global '%s.%s' is forbidden" %
                                     (module, name))


""" Command Aliases """


def add_alias(rest):

    aliases = config.sections["server"]["command_aliases"]

    if rest:
        args = rest.split(" ", 1)

        if len(args) == 2:
            if args[0] in ("alias", "unalias"):
                return "I will not alias that!\n"

            aliases[args[0]] = args[1]

        if args[0] in aliases:
            return "Alias %s: %s\n" % (args[0], aliases[args[0]])

        return _("No such alias (%s)") % rest + "\n"

    msg = "\n" + _("Aliases:") + "\n"

    for (key, value) in aliases.items():
        msg = msg + "%s: %s\n" % (key, value)

    return msg + "\n"


def unalias(rest):

    aliases = config.sections["server"]["command_aliases"]

    if rest and rest in aliases:
        action = aliases[rest]
        del aliases[rest]

        return _("Removed alias %(alias)s: %(action)s\n") % {'alias': rest, 'action': action}

    return _("No such alias (%(alias)s)\n") % {'alias': rest}


def is_alias(cmd):

    if not cmd:
        return False

    if cmd[0] != "/":
        return False

    cmd = cmd[1:].split(" ")

    if cmd[0] in config.sections["server"]["command_aliases"]:
        return True

    return False


def expand_alias(cmd):
    output = _expand_alias(config.sections["server"]["command_aliases"], cmd)
    return output


def _expand_alias(aliases, cmd):

    def getpart(line):
        if line[0] != "(":
            return ""
        i = 1
        ret = ""
        level = 0
        while i < len(line):
            if line[i] == "(":
                level = level + 1
            if line[i] == ")":
                if level == 0:
                    return ret
                level = level - 1
            ret = ret + line[i]
            i = i + 1
        return ""

    if not is_alias(cmd):
        return None
    try:
        cmd = cmd[1:].split(" ")
        alias = aliases[cmd[0]]
        ret = ""
        i = 0
        while i < len(alias):
            if alias[i:i + 2] == "$(":
                arg = getpart(alias[i + 1:])
                if not arg:
                    ret = ret + "$"
                    i = i + 1
                    continue
                i = i + len(arg) + 3
                args = arg.split("=", 1)
                if len(args) > 1:
                    default = args[1]
                else:
                    default = ""
                args = args[0].split(":")
                if len(args) == 1:
                    first = last = int(args[0])
                else:
                    if args[0]:
                        first = int(args[0])
                    else:
                        first = 1
                    if args[1]:
                        last = int(args[1])
                    else:
                        last = len(cmd)
                value = " ".join(cmd[first:last + 1])
                if not value:
                    value = default
                ret = ret + value
            else:
                ret = ret + alias[i]
                i = i + 1
        return ret
    except Exception as error:
        log.add("%s", error)

    return ""


""" Chat Completion """


def get_completion_list(commands, rooms):

    config_words = config.sections["words"]

    if not config_words["tab"]:
        return []

    completion_list = [config.sections["server"]["login"], "nicotine"]

    if config_words["roomnames"]:
        completion_list += rooms

    if config_words["buddies"]:
        for i in config.sections["server"]["userlist"]:
            if i and isinstance(i, list):
                user = str(i[0])
                completion_list.append(user)

    if config_words["aliases"]:
        for k in config.sections["server"]["command_aliases"].keys():
            completion_list.append("/" + str(k))

    if config_words["commands"]:
        completion_list += commands

    return completion_list


""" Debugging """


def debug(*args):
    """ Prints debugging info. """

    truncated_args = [arg[:200] if isinstance(arg, str) else arg for arg in args]
    print('*' * 8, truncated_args)


def strace(function):
    """ Decorator for debugging """

    from itertools import chain

    def newfunc(*args, **kwargs):
        name = function.__name__
        print(("%s(%s)" % (name, ", ".join(map(repr, chain(args, list(kwargs.values())))))))
        retvalue = function(*args, **kwargs)
        print(("%s(%s): %s" % (name, ", ".join(map(repr, chain(args, list(kwargs.values())))), repr(retvalue))))
        return retvalue

    return newfunc
