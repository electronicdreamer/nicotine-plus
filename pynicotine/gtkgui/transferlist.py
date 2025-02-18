# COPYRIGHT (C) 2020-2021 Nicotine+ Team
# COPYRIGHT (C) 2018 Mutnick <mutnick@techie.com>
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2008-2011 Quinox <quinox@users.sf.net>
# COPYRIGHT (C) 2009 Hedonist <ak@sensi.org>
# COPYRIGHT (C) 2006-2009 Daelstorm <daelstorm@gmail.com>
# COPYRIGHT (C) 2003-2004 Hyriand <hyriand@thegraveyard.org>
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

import os

from sys import maxsize
from time import time

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from pynicotine.config import config
from pynicotine.gtkgui.fileproperties import FileProperties
from pynicotine.gtkgui.utils import connect_key_press_event
from pynicotine.gtkgui.utils import copy_file_url
from pynicotine.gtkgui.utils import copy_text
from pynicotine.gtkgui.utils import get_key_press_event_args
from pynicotine.gtkgui.utils import load_ui_elements
from pynicotine.gtkgui.utils import parse_accelerator
from pynicotine.gtkgui.widgets.popupmenu import PopupMenu
from pynicotine.gtkgui.widgets.theme import update_widget_visuals
from pynicotine.gtkgui.widgets.treeview import collapse_treeview
from pynicotine.gtkgui.widgets.treeview import create_grouping_menu
from pynicotine.gtkgui.widgets.treeview import initialise_columns
from pynicotine.gtkgui.widgets.treeview import save_columns
from pynicotine.gtkgui.widgets.treeview import select_user_row_iter
from pynicotine.gtkgui.widgets.treeview import show_file_path_tooltip
from pynicotine.gtkgui.widgets.treeview import verify_grouping_mode
from pynicotine.transfers import Transfer
from pynicotine.utils import human_size
from pynicotine.utils import human_speed


class TransferList:

    def __init__(self, frame, type):

        self.frame = frame
        self.type = type

        load_ui_elements(self, os.path.join(frame.gui_dir, "ui", type + "s.ui"))
        getattr(frame, type + "svbox").add(self.Main)

        grouping_button = getattr(frame, "ToggleTree%ss" % self.type.title())

        if Gtk.get_major_version() == 4:
            grouping_button.set_icon_name("view-list-symbolic")

            self.ClearTransfers.set_has_frame(False)
            self.ClearTransfers.set_label(self.ClearTransfersLabel.get_first_child().get_text())
        else:
            grouping_button.set_image(Gtk.Image.new_from_icon_name("view-list-symbolic", Gtk.IconSize.BUTTON))

            self.ClearTransfers.add(self.ClearTransfersLabel)

        self.key_controller = connect_key_press_event(self.Transfers, self.on_key_press_event)

        self.last_ui_update = self.last_save = 0
        self.transfer_list = []
        self.users = {}
        self.paths = {}

        # Status list
        self.statuses = {}
        self.statuses["Queued"] = _("Queued")
        self.statuses["Getting status"] = _("Getting status")
        self.statuses["Establishing connection"] = _("Establishing connection")
        self.statuses["Transferring"] = _("Transferring")
        self.statuses["Cannot connect"] = _("Cannot connect")
        self.statuses["User logged off"] = _("User logged off")
        self.statuses["Connection closed by peer"] = _("Connection closed by peer")
        self.statuses["Disallowed extension"] = _("Disallowed extension")  # Sent by Soulseek NS for filtered extensions
        self.statuses["Aborted"] = _("Aborted")
        self.statuses["Finished"] = _("Finished")
        self.statuses["Filtered"] = _("Filtered")
        self.statuses["File not shared"] = _("File not shared")
        self.statuses["File not shared."] = _("File not shared")  # The official client sends a variant containing a dot
        self.statuses["Download folder error"] = _("Download folder error")
        self.statuses["Local file error"] = _("Local file error")
        self.statuses["Remote file error"] = _("Remote file error")

        # String templates
        self.extension_list_template = _("All %(ext)s")
        self.files_template = _("%(number)2s files ")

        self.transfersmodel = Gtk.TreeStore(
            str,                   # (0)  user
            str,                   # (1)  path
            str,                   # (2)  file name
            str,                   # (3)  status
            str,                   # (4)  hqueue position
            GObject.TYPE_UINT64,   # (5)  percent
            str,                   # (6)  hsize
            str,                   # (7)  hspeed
            str,                   # (8)  htime elapsed
            str,                   # (9)  time left
            str,                   # (10) path
            str,                   # (11) status (non-translated)
            GObject.TYPE_UINT64,   # (12) size
            GObject.TYPE_UINT64,   # (13) current bytes
            GObject.TYPE_UINT64,   # (14) speed
            GObject.TYPE_UINT64,   # (15) time elapsed
            GObject.TYPE_UINT64,   # (16) file count
            GObject.TYPE_UINT64,   # (17) queue position
            GObject.TYPE_PYOBJECT  # (18) transfer object
        )

        self.column_numbers = list(range(self.transfersmodel.get_n_columns()))
        self.cols = cols = initialise_columns(
            type, self.Transfers,
            ["user", _("User"), 200, "text", None],
            ["path", _("Path"), 400, "text", None],
            ["filename", _("Filename"), 400, "text", None],
            ["status", _("Status"), 140, "text", None],
            ["queue_position", _("Queue Position"), 50, "number", None],
            ["percent", _("Percent"), 70, "progress", None],
            ["size", _("Size"), 170, "number", None],
            ["speed", _("Speed"), 90, "number", None],
            ["time_elapsed", _("Time Elapsed"), 140, "number", None],
            ["time_left", _("Time Left"), 140, "number", None],
        )

        cols["user"].set_sort_column_id(0)
        cols["path"].set_sort_column_id(1)
        cols["filename"].set_sort_column_id(2)
        cols["status"].set_sort_column_id(11)
        cols["queue_position"].set_sort_column_id(17)
        cols["percent"].set_sort_column_id(5)
        cols["size"].set_sort_column_id(12)
        cols["speed"].set_sort_column_id(14)
        cols["time_elapsed"].set_sort_column_id(8)
        cols["time_left"].set_sort_column_id(9)

        self.Transfers.set_model(self.transfersmodel)

        self.expand_button = getattr(frame, "Expand%ss" % self.type.title())

        state = GLib.Variant.new_string(verify_grouping_mode(config.sections["transfers"]["group%ss" % self.type]))
        action = Gio.SimpleAction.new_stateful("%sgrouping" % self.type, GLib.VariantType.new("s"), state)
        action.connect("change-state", self.on_toggle_tree)
        frame.MainWindow.add_action(action)
        action.change_state(state)

        menu = create_grouping_menu(
            frame.MainWindow, config.sections["transfers"]["group%ss" % self.type], self.on_toggle_tree)
        grouping_button.set_menu_model(menu)

        self.expand_button.connect("toggled", self.on_expand_tree)
        self.expand_button.set_active(config.sections["transfers"]["%ssexpanded" % self.type])

        self.popup_menu_users = PopupMenu(frame)
        self.popup_menu_clear = PopupMenu(frame)
        self.ClearTransfers.set_menu_model(self.popup_menu_clear)

        self.popup_menu = PopupMenu(frame, self.Transfers, self.on_popup_menu)
        self.popup_menu.setup(
            ("#" + "selected_files", None),
            ("", None),
            ("#" + _("Send to _Player"), self.on_play_files),
            ("#" + _("_Open in File Manager"), self.on_open_directory),
            ("", None),
            ("#" + _("Copy _File Path"), self.on_copy_file_path),
            ("#" + _("Copy _URL"), self.on_copy_url),
            ("#" + _("Copy Folder URL"), self.on_copy_dir_url),
            ("", None),
            ("#" + _("_Search"), self.on_file_search),
            ("#" + _("_Browse Folder(s)"), self.on_browse_folder),
            ("#" + _("File P_roperties"), self.on_file_properties),
            (">" + _("User(s)"), self.popup_menu_users),
            ("", None),
            ("#" + _("_Retry"), self.on_retry_transfer),
            ("#" + _("Abor_t"), self.on_abort_transfer),
            ("#" + _("_Clear"), self.on_clear_transfer),
            ("", None),
            (">" + _("Clear Groups"), self.popup_menu_clear)
        )

        self.update_visuals()

    def server_login(self):

        self.transfer_list = getattr(self.frame.np.transfers, "%ss" % self.type)
        self.Transfers.set_sensitive(True)
        self.update()

    def server_disconnect(self):

        self.Transfers.set_sensitive(False)
        self.clear()
        self.transfer_list = []

    def rebuild_transfers(self):
        self.clear()
        self.update()

    def save_columns(self):
        save_columns(self.type, self.Transfers.get_columns())

    def update_visuals(self):

        for widget in list(self.__dict__.values()):
            update_widget_visuals(widget, list_font_target="transfersfont")

    def select_transfers(self):

        self.selected_transfers = set()
        self.selected_users = set()

        model, paths = self.Transfers.get_selection().get_selected_rows()

        for path in paths:
            iterator = model.get_iter(path)
            self.select_transfer(model, iterator, select_user=True)

            # If we're in grouping mode, select any transfers under the selected
            # user or folder
            self.select_child_transfers(model, model.iter_children(iterator))

    def select_child_transfers(self, model, iterator):

        while iterator is not None:
            self.select_transfer(model, iterator)
            self.select_child_transfers(model, model.iter_children(iterator))
            iterator = model.iter_next(iterator)

    def select_transfer(self, model, iterator, select_user=False):

        user = model.get_value(iterator, 0)
        transfer = model.get_value(iterator, 18)

        if isinstance(transfer, Transfer):
            self.selected_transfers.add(transfer)

        if select_user:
            self.selected_users.add(user)

    def new_transfer_notification(self):
        self.frame.request_tab_icon(self.tab_label)

    def on_ban(self, *args):

        self.select_transfers()

        for user in self.selected_users:
            self.frame.np.network_filter.ban_user(user)

    def on_file_search(self, *args):

        transfer = next(iter(self.selected_transfers), None)

        if not transfer:
            return

        self.frame.SearchEntry.set_text(transfer.filename.rsplit("\\", 1)[1])
        self.frame.change_main_page("search")

    def translate_status(self, status):

        try:
            newstatus = self.statuses[status]
        except KeyError:
            newstatus = status

        return newstatus

    def update(self, transfer=None, forceupdate=False):

        if not self.Transfers.get_sensitive():
            """ List is not initialized """
            return

        curtime = time()

        if (curtime - self.last_save) > 15:

            """ Save list of transfers to file every 15 seconds """

            if self.frame.np.transfers is not None:
                self.frame.np.transfers.save_transfers("downloads")
                self.frame.np.transfers.save_transfers("uploads")

            self.last_save = curtime

        finished = (transfer is not None and transfer.status == "Finished")

        if forceupdate or finished or (curtime - self.last_ui_update) > 1:
            self.frame.update_bandwidth()

        if not forceupdate and self.frame.current_tab_label != self.tab_label:
            """ No need to do unnecessary work if transfers are not visible """
            return

        if transfer is not None:
            self.update_specific(transfer)

        elif self.transfer_list:
            for transfer in reversed(self.transfer_list):
                self.update_specific(transfer)

        if forceupdate or finished or (curtime - self.last_ui_update) > 1:

            """ Unless a transfer finishes, use a cooldown to avoid updating
            too often """

            self.update_parent_rows()

    def update_parent_rows(self, only_remove=False):

        # Remove empty parent rows
        for path, pathiter in list(self.paths.items()):
            if not self.transfersmodel.iter_has_child(pathiter):
                self.transfersmodel.remove(pathiter)
                del self.paths[path]

            elif not only_remove:
                self.update_parent_row(pathiter)

        for username, useriter in list(self.users.items()):
            if isinstance(useriter, Gtk.TreeIter):
                if not self.transfersmodel.iter_has_child(useriter):
                    self.transfersmodel.remove(useriter)
                    del self.users[username]

                elif not only_remove:
                    self.update_parent_row(useriter)
            else:
                # No grouping
                if not self.users[username]:
                    del self.users[username]

        self.frame.update_bandwidth()
        self.last_ui_update = time()

    def update_parent_row(self, initer):

        speed = 0.0
        percent = totalsize = position = 0
        hspeed = helapsed = left = ""
        elapsed = 0
        filecount = 0
        salientstatus = ""
        extensions = {}

        iterator = self.transfersmodel.iter_children(initer)

        while iterator is not None:

            status = self.transfersmodel.get_value(iterator, 11)

            if salientstatus in ('', "Finished", "Filtered"):  # we prefer anything over ''/finished
                salientstatus = status

            filename = self.transfersmodel.get_value(iterator, 2)
            parts = filename.rsplit('.', 1)

            if len(parts) == 2:
                ext = parts[1]
                try:
                    extensions[ext.lower()] += 1
                except KeyError:
                    extensions[ext.lower()] = 1

            filecount += self.transfersmodel.get_value(iterator, 16)

            if status == "Filtered":
                # We don't want to count filtered files when calculating the progress
                iterator = self.transfersmodel.iter_next(iterator)
                continue

            elapsed += self.transfersmodel.get_value(iterator, 15)
            totalsize += self.transfersmodel.get_value(iterator, 12)
            position += self.transfersmodel.get_value(iterator, 13)

            if status == "Transferring":
                speed += float(self.transfersmodel.get_value(iterator, 14))
                left = self.transfersmodel.get_value(iterator, 9)

            if status in ("Transferring", "Banned", "Getting address", "Establishing connection"):
                salientstatus = status

            iterator = self.transfersmodel.iter_next(iterator)

        if totalsize > 0:
            percent = min(((100 * position) / totalsize), 100)
        else:
            percent = 100

        if speed > 0:
            hspeed = human_speed(speed)
            left = self.frame.np.transfers.get_time((totalsize - position) / speed)

        if elapsed > 0:
            helapsed = self.frame.np.transfers.get_time(elapsed)

        if not extensions:
            extensions = ""
        elif len(extensions) == 1:
            extensions = " (" + self.extension_list_template % {'ext': next(iter(extensions))} + ")"
        else:
            extensions = " (" + ", ".join((str(count) + " " + ext for (ext, count) in extensions.items())) + ")"

        self.transfersmodel.set_value(initer, 2, self.files_template % {'number': filecount} + extensions)
        self.transfersmodel.set_value(initer, 3, self.translate_status(salientstatus))
        self.transfersmodel.set_value(initer, 5, GObject.Value(GObject.TYPE_UINT64, percent))
        self.transfersmodel.set_value(initer, 6, "%s / %s" % (human_size(position), human_size(totalsize)))
        self.transfersmodel.set_value(initer, 7, hspeed)
        self.transfersmodel.set_value(initer, 8, helapsed)
        self.transfersmodel.set_value(initer, 9, left)
        self.transfersmodel.set_value(initer, 11, salientstatus)
        self.transfersmodel.set_value(initer, 12, GObject.Value(GObject.TYPE_UINT64, totalsize))
        self.transfersmodel.set_value(initer, 13, GObject.Value(GObject.TYPE_UINT64, position))
        self.transfersmodel.set_value(initer, 14, GObject.Value(GObject.TYPE_UINT64, speed))
        self.transfersmodel.set_value(initer, 15, GObject.Value(GObject.TYPE_UINT64, elapsed))
        self.transfersmodel.set_value(initer, 16, GObject.Value(GObject.TYPE_UINT64, filecount))

    def update_specific(self, transfer=None):

        currentbytes = transfer.currentbytes
        place = transfer.place or 0
        hplace = ""

        if place > 0:
            hplace = str(place)

        hspeed = helapsed = ""

        if currentbytes is None:
            currentbytes = 0

        status = transfer.status or ""
        hstatus = self.translate_status(status)

        try:
            size = int(transfer.size)
            if size < 0 or size > maxsize:
                size = 0
        except TypeError:
            size = 0

        hsize = "%s / %s" % (human_size(currentbytes), human_size(size))

        if transfer.modifier:
            hsize += " (%s)" % transfer.modifier

        speed = transfer.speed or 0
        elapsed = transfer.timeelapsed or 0
        left = transfer.timeleft or ""

        if speed > 0:
            speed = float(speed)
            hspeed = human_speed(speed)

        if elapsed > 0:
            helapsed = self.frame.np.transfers.get_time(elapsed)

        try:
            icurrentbytes = int(currentbytes)
            percent = min(((100 * icurrentbytes) / int(size)), 100)

        except Exception:
            icurrentbytes = 0
            percent = 100

        # Modify old transfer
        if transfer.iterator is not None:
            initer = transfer.iterator

            self.transfersmodel.set_value(initer, 3, hstatus)
            self.transfersmodel.set_value(initer, 4, hplace)
            self.transfersmodel.set_value(initer, 5, GObject.Value(GObject.TYPE_UINT64, percent))
            self.transfersmodel.set_value(initer, 6, hsize)
            self.transfersmodel.set_value(initer, 7, hspeed)
            self.transfersmodel.set_value(initer, 8, helapsed)
            self.transfersmodel.set_value(initer, 9, left)
            self.transfersmodel.set_value(initer, 11, status)
            self.transfersmodel.set_value(initer, 12, GObject.Value(GObject.TYPE_UINT64, size))
            self.transfersmodel.set_value(initer, 13, GObject.Value(GObject.TYPE_UINT64, currentbytes))
            self.transfersmodel.set_value(initer, 14, GObject.Value(GObject.TYPE_UINT64, speed))
            self.transfersmodel.set_value(initer, 15, GObject.Value(GObject.TYPE_UINT64, elapsed))
            self.transfersmodel.set_value(initer, 17, GObject.Value(GObject.TYPE_UINT64, place))
            return

        fn = transfer.filename
        user = transfer.user
        shortfn = fn.split("\\")[-1]
        filecount = 1

        if self.tree_users != "ungrouped":
            # Group by folder or user

            empty_int = 0
            empty_str = ""

            if user not in self.users:
                # Create Parent if it doesn't exist
                # ProgressRender not visible (last column sets 4th column)
                self.users[user] = self.transfersmodel.insert_with_values(
                    None, -1, self.column_numbers,
                    [
                        user,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_int,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_str,
                        empty_int,
                        empty_int,
                        empty_int,
                        empty_int,
                        filecount,
                        empty_int,
                        lambda: None
                    ]
                )

            parent = self.users[user]

            if self.tree_users == "folder_grouping":
                # Group by folder

                """ Paths can be empty if files are downloaded individually, make sure we
                don't add files to the wrong user in the TreeView """
                path = transfer.path
                user_path = user + path

                if config.sections["ui"]["reverse_file_paths"]:
                    path = '/'.join(reversed(path.split('/')))

                if user_path not in self.paths:
                    self.paths[user_path] = self.transfersmodel.insert_with_values(
                        self.users[user], -1, self.column_numbers,
                        [
                            user,
                            path,
                            empty_str,
                            empty_str,
                            empty_str,
                            empty_int,
                            empty_str,
                            empty_str,
                            empty_str,
                            empty_str,
                            empty_str,
                            empty_str,
                            empty_int,
                            empty_int,
                            empty_int,
                            empty_int,
                            filecount,
                            empty_int,
                            lambda: None
                        ]
                    )

                parent = self.paths[user_path]
        else:
            # No grouping
            # We use this list to get the total number of users
            self.users.setdefault(user, set()).add(transfer)
            parent = None

        # Add a new transfer
        if self.tree_users == "folder_grouping":
            # Group by folder, path not visible
            path = ""
        else:
            path = transfer.path

            if config.sections["ui"]["reverse_file_paths"]:
                path = '/'.join(reversed(path.split('/')))

        iterator = self.transfersmodel.insert_with_values(
            parent, -1, self.column_numbers,
            (
                user,
                path,
                shortfn,
                hstatus,
                hplace,
                GObject.Value(GObject.TYPE_UINT64, percent),
                hsize,
                hspeed,
                helapsed,
                left,
                fn,
                status,
                GObject.Value(GObject.TYPE_UINT64, size),
                GObject.Value(GObject.TYPE_UINT64, icurrentbytes),
                GObject.Value(GObject.TYPE_UINT64, speed),
                GObject.Value(GObject.TYPE_UINT64, elapsed),
                GObject.Value(GObject.TYPE_UINT64, filecount),
                GObject.Value(GObject.TYPE_UINT64, place),
                transfer
            )
        )
        transfer.iterator = iterator

        # Expand path
        if parent is not None:
            transfer_path = self.transfersmodel.get_path(iterator)

            if self.tree_users == "folder_grouping":
                # Group by folder, we need the user path to expand it
                user_path = self.transfersmodel.get_path(self.users[user])
            else:
                user_path = None

            self.expand(transfer_path, user_path)

    def retry_transfers(self):
        for transfer in self.selected_transfers:
            getattr(self.frame.np.transfers, "retry_" + self.type)(transfer)

    def abort_transfers(self, clear=False):

        for transfer in self.selected_transfers:
            if transfer.status != "Finished":
                self.frame.np.transfers.abort_transfer(transfer, send_fail_message=True)

                if not clear:
                    transfer.status = "Aborted"
                    self.update(transfer)

            if clear:
                self.remove_specific(transfer)

    def remove_specific(self, transfer, cleartreeviewonly=False):

        user = transfer.user

        if user in self.users and not isinstance(self.users[user], Gtk.TreeIter):
            # No grouping
            self.users[user].discard(transfer)

        if transfer in self.frame.np.transfers.transfer_request_times:
            del self.frame.np.transfers.transfer_request_times[transfer]

        if not cleartreeviewonly:
            self.transfer_list.remove(transfer)

        if transfer.iterator is not None:
            self.transfersmodel.remove(transfer.iterator)

        self.update_parent_rows(only_remove=True)

    def clear_transfers(self, status):

        for transfer in self.transfer_list.copy():
            if transfer.status in status:
                self.frame.np.transfers.abort_transfer(transfer, send_fail_message=True)
                self.remove_specific(transfer)

    def clear(self):

        self.users.clear()
        self.paths.clear()
        self.selected_transfers = set()
        self.selected_users = set()
        self.transfersmodel.clear()

        for transfer in self.transfer_list:
            transfer.iterator = None

    def add_popup_menu_user(self, popup, user):

        popup.setup_user_menu(user)
        popup.setup(
            ("", None),
            ("#" + _("Select User's Transfers"), self.on_select_user_transfers, user)
        )

        popup.toggle_user_items()

    def populate_popup_menu_users(self):

        self.popup_menu_users.clear()

        if not self.selected_users:
            return

        # Multiple users, create submenus for each user
        if len(self.selected_users) > 1:
            for user in self.selected_users:
                popup = PopupMenu(self.frame)
                self.add_popup_menu_user(popup, user)
                self.popup_menu_users.setup(
                    (">" + user, popup)
                )
            return

        # Single user, add items directly to "User(s)" submenu
        user = next(iter(self.selected_users), None)
        self.add_popup_menu_user(self.popup_menu_users, user)

    def expand(self, transfer_path, user_path):

        if self.expand_button.get_active():
            self.Transfers.expand_to_path(transfer_path)

        elif user_path and self.tree_users == "folder_grouping":
            # Group by folder, show user folders in collapsed mode

            self.Transfers.expand_to_path(user_path)

    def on_expand_tree(self, widget):

        expand_button_icon = getattr(self.frame, "Expand%ssImage" % self.type.title())
        expanded = widget.get_active()

        if expanded:
            icon_name = "go-up-symbolic"
            self.Transfers.expand_all()

        else:
            icon_name = "go-down-symbolic"
            collapse_treeview(self.Transfers, self.tree_users)

        expand_button_icon.set_property("icon-name", icon_name)

        config.sections["transfers"]["%ssexpanded" % self.type] = expanded
        config.write_configuration()

    def on_toggle_tree(self, action, state):

        mode = state.get_string()
        active = mode != "ungrouped"

        config.sections["transfers"]["group%ss" % self.type] = mode
        self.Transfers.set_show_expanders(active)
        self.expand_button.set_visible(active)

        self.tree_users = mode
        self.rebuild_transfers()

        action.set_state(state)

    def on_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        return show_file_path_tooltip(widget, x, y, tooltip, 10)

    def on_popup_menu(self, menu, widget):

        self.select_transfers()
        num_selected_transfers = len(self.selected_transfers)

        actions = menu.get_actions()
        users = len(self.selected_users) > 0
        files = num_selected_transfers > 0

        actions[_("User(s)")].set_enabled(users)  # Users Menu
        self.populate_popup_menu_users()

        if files:
            act = True
        else:
            # Disable options
            # Send to player, File manager, file properties, Copy File Path, Copy URL, Copy Folder URL, Search filename
            act = False

        for i in (_("Send to _Player"), _("_Open in File Manager"), _("File P_roperties"),
                  _("Copy _File Path"), _("Copy _URL"), _("Copy Folder URL"), _("_Search")):
            actions[i].set_enabled(act)

        if not users or not files:
            # Disable options
            # Retry, Abort, Clear
            act = False
        else:
            act = True

        for i in (_("_Retry"), _("Abor_t"), _("_Clear")):
            actions[i].set_enabled(act)

        menu.set_num_selected_files(num_selected_transfers)

    def on_row_activated(self, treeview, path, column):

        self.select_transfers()
        dc = config.sections["transfers"]["%s_doubleclick" % self.type]

        if dc == 1:  # Send to player
            self.on_play_files()
        elif dc == 2:  # File manager
            self.on_open_directory()
        elif dc == 3:  # Search
            self.on_file_search()
        elif dc == 4:  # Abort
            self.abort_transfers()
        elif dc == 5:  # Clear
            self.abort_transfers(clear=True)
        elif dc == 6:  # Retry
            self.retry_transfers()

    def on_select_user_transfers(self, *args):

        if not self.selected_users:
            return

        selected_user = args[-1]

        sel = self.Transfers.get_selection()
        fmodel = self.Transfers.get_model()
        sel.unselect_all()

        iterator = fmodel.get_iter_first()

        select_user_row_iter(fmodel, sel, 0, selected_user, iterator)

        self.select_transfers()

    def on_key_press_event(self, *args):

        keyval, keycode, state = get_key_press_event_args(*args)
        self.select_transfers()

        keycodes, mods = parse_accelerator("t")

        if keycode in keycodes:
            self.abort_transfers()
            return True

        keycodes, mods = parse_accelerator("r")

        if keycode in keycodes:
            self.retry_transfers()
            return True

        keycodes, mods = parse_accelerator("<Primary>c")

        if state & mods and keycode in keycodes:
            self.on_copy_file_path()
            return True

        keycodes, mods = parse_accelerator("Delete")

        if keycode in keycodes:
            self.abort_transfers(clear=True)
            return True

        # No key match, continue event
        return False

    def on_file_properties(self, *args):

        data = []

        for transfer in self.selected_transfers:
            user = transfer.user
            fullname = transfer.filename
            filename = fullname.split("\\")[-1]
            size = speed = length = queue = immediate = num = country = bitratestr = ""

            size = str(human_size(transfer.size))

            if transfer.speed:
                speed = str(human_speed(transfer.speed))

            bitratestr = str(transfer.bitrate)
            length = str(transfer.length)

            directory = fullname.rsplit("\\", 1)[0]

            data.append({
                "user": user,
                "fn": fullname,
                "position": num,
                "filename": filename,
                "directory": directory,
                "size": size,
                "speed": speed,
                "queue": queue,
                "immediate": immediate,
                "bitrate": bitratestr,
                "length": length,
                "country": country
            })

        if data:
            FileProperties(self.frame, data).show()

    def on_copy_file_path(self, *args):

        transfer = next(iter(self.selected_transfers), None)

        if transfer:
            copy_text(transfer.filename)

    def on_copy_url(self, *args):

        transfer = next(iter(self.selected_transfers), None)

        if transfer:
            copy_file_url(transfer.user, transfer.filename)

    def on_copy_dir_url(self, *args):

        transfer = next(iter(self.selected_transfers), None)

        if transfer:
            copy_file_url(transfer.user, transfer.filename.rsplit('\\', 1)[0] + '\\')

    def on_retry_transfer(self, *args):
        self.select_transfers()
        self.retry_transfers()

    def on_abort_transfer(self, *args):
        self.select_transfers()
        self.abort_transfers()

    def on_clear_transfer(self, *args):
        self.select_transfers()
        self.abort_transfers(clear=True)

    def on_clear_response(self, dialog, response_id, data):

        dialog.destroy()

        if response_id == Gtk.ResponseType.OK:
            if data == "queued":
                self.clear_transfers(["Queued"])

            elif data == "all":
                self.clear()

    def on_clear_queued(self, *args):
        self.clear_transfers(["Queued"])

    def on_clear_finished(self, *args):
        self.clear_transfers(["Finished"])
