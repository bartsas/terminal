#!/usr/bin/python3

import configparser
import csv
import gi
import html
import os.path
import pykeepass
import shlex
import sys
import urllib.parse

gi.require_version("Gdk", "3.0")
import gi.repository.Gdk as gdk

gi.require_version("GdkPixbuf", "2.0")
import gi.repository.GdkPixbuf as pixbuf

gi.require_version("Gio", "2.0")
import gi.repository.Gio as gio

gi.require_version("GLib", "2.0")
import gi.repository.GLib as glib

gi.require_version("GObject", "2.0")
import gi.repository.GObject as gobject

gi.require_version("Gtk", "3.0")
import gi.repository.Gtk as gtk

gi.require_version("Notify", "0.7")
import gi.repository.Notify as notify

gi.require_version("Vte", "2.91")
import gi.repository.Vte as vte

def return_character(character):
    return lambda lookup_variable: character

def get_variable(name):
    return lambda lookup_variable: lookup_variable(name)

def compile_snippet(snippet):
    ESCAPE_CHARS = {
        "t":  "\t",
        "n":  "\n",
        "r":  "\r",
        "e":  "\x1B",
        "[":  "\x1B[",
        "$":  "$",
        "\\": "\\",
        "'":  "'",
        "\"": "\""}

    result = []

    try:
        iterator = enumerate(snippet)
        position, character = next(iterator)

        while True:
            if character == "\\":
                try:
                    position, character = next(iterator)

                    if character == "^":
                        position, character = next(iterator)
                        control_character = ord(character) - ord("@")

                        if not 0 <= control_character < 0x20:
                            raise Exception(f"invalid control character '{character:s}' at position {position:d} of snippet '{snippet:s}'")

                        result.append(return_character(chr(control_character)))
                    else:
                        escape_char = ESCAPE_CHARS.get(character)

                        if escape_char is None:
                            raise Exception(f"invalid escape character '{character:s}' at position {position:d} of snippet '{snippet:s}'")

                        result.append(return_character(escape_char))
                except StopIteration:
                    raise Exception(f"unexpected end of snippet '{snippet:s}'")

                position, character = next(iterator)
            elif character == "$":
                try:
                    position, character = next(iterator)

                    if character == "{":
                        try:
                            position, character = next(iterator)

                            if not character.isalpha():
                                raise Exception(f"unexpected character '{character:s}' at position {position:d} of snippet '{snippet:s}'")

                            name = ""

                            while character.isalnum():
                                name += character
                                position, character = next(iterator)

                            if character != "}":
                                raise Exception(f"unexpected character '{character:s}' at position {position:d} of snippet '{snippet:s}'")

                            result.append(get_variable(name))
                        except StopIteration:
                            raise Exception(f"unexpected end of snippet '{snippet:s}'")

                        position, character = next(iterator)
                    elif character.isalpha():
                        name = ""

                        try:
                            while character.isalnum():
                                name += character
                                position, character = next(iterator)
                        except StopIteration:
                            # The end of the input has been reached so break from the main loop.
                            break
                        finally:
                            # Append the variable to the result regardless of whether the end of the input has been reached or not.
                            result.append(get_variable(name))
                    else:
                        raise Exception(f"unexpected character '{character:s}' at position {position:d} of snippet '{snippet:s}'")
                except StopIteration:
                    raise Exception(f"unexpected end of snippet '{snippet:s}'")
            else:
                result.append(return_character(character))
                position, character = next(iterator)
    except StopIteration:
        pass

    return tuple(result)

class Terminal(gtk.ScrolledWindow):
    __NOTIFICATION_TRIGGER_TIME = 4000
    __COLOR_PALETTE = (
        gdk.RGBA(0.00, 0.00, 0.00), # Black
        gdk.RGBA(0.80, 0.19, 0.19), # Red
        gdk.RGBA(0.05, 0.74, 0.47), # Green
        gdk.RGBA(0.90, 0.90, 0.06), # Yellow
        gdk.RGBA(0.14, 0.45, 0.78), # Blue
        gdk.RGBA(0.74, 0.25, 0.74), # Magenta
        gdk.RGBA(0.07, 0.66, 0.80), # Cyan
        gdk.RGBA(0.90, 0.90, 0.90), # White
        gdk.RGBA(0.40, 0.40, 0.40), # Bright Black (Gray)
        gdk.RGBA(0.95, 0.30, 0.30), # Bright Red
        gdk.RGBA(0.14, 0.82, 0.55), # Bright Green
        gdk.RGBA(0.96, 0.96, 0.26), # Bright Yellow
        gdk.RGBA(0.23, 0.56, 0.92), # Bright Blue
        gdk.RGBA(0.84, 0.44, 0.84), # Bright Magenta
        gdk.RGBA(0.16, 0.72, 0.86), # Bright Cyan
        gdk.RGBA(0.90, 0.90, 0.90)) # Bright White
        #gdk.RGBA(0.20, 0.20, 0.20), # Black
        #gdk.RGBA(0.80, 0.00, 0.00), # Red
        #gdk.RGBA(0.00, 0.80, 0.00), # Green
        #gdk.RGBA(0.80, 0.80, 0.00), # Yellow
        #gdk.RGBA(0.00, 0.00, 0.93), # Blue
        #gdk.RGBA(0.80, 0.00, 0.80), # Magenta
        #gdk.RGBA(0.00, 0.80, 0.80), # Cyan
        #gdk.RGBA(0.90, 0.90, 0.90), # White
        #gdk.RGBA(0.50, 0.50, 0.50), # Bright Black (Gray)
        #gdk.RGBA(1.00, 0.00, 0.00), # Bright Red
        #gdk.RGBA(0.00, 1.00, 0.00), # Bright Green
        #gdk.RGBA(1.00, 1.00, 0.00), # Bright Yellow
        #gdk.RGBA(0.36, 0.36, 1.00), # Bright Blue
        #gdk.RGBA(1.00, 0.00, 1.00), # Bright Magenta
        #gdk.RGBA(0.00, 1.00, 1.00), # Bright Cyan
        #gdk.RGBA(1.00, 1.00, 1.00)) # Bright White

    __gsignals__ = {
        "changed": (gobject.SignalFlags.RUN_LAST, gobject.TYPE_NONE, ()),
        "duplicated": (gobject.SignalFlags.RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, gobject.TYPE_STRING, gobject.TYPE_PYOBJECT, gobject.TYPE_STRING)),
        "closed": (gobject.SignalFlags.RUN_LAST, gobject.TYPE_NONE, ())}

    def __init__(self, window, icons, snippets, title, notifications_enabled, icon_name, command, working_dir):
        super(Terminal, self).__init__()

        self.__window                = window
        self.__icons                 = icons
        self.__snippets              = snippets
        self.__title                 = title
        self.__icon_name             = icon_name
        self.__command               = command
        self.__initial_working_dir   = os.path.expanduser(working_dir)
        self.__notifications_enabled = notifications_enabled
        self.__notification_timeout  = None
        self.__stored_password       = None

        self.__notification = notify.Notification.new("SHOULD HAVE BEEN UPDATED", "SHOULD HAVE BEEN UPDATED", "dialog-error")

        self.__properties_item = gtk.MenuItem.new_with_label("Properties")
        self.__properties_item.connect("activate", self.__handle_properties_item_activated)
        self.__properties_item.show()

        self.__duplicate_item = gtk.MenuItem.new_with_label("Duplicate")
        self.__duplicate_item.connect("activate", self.__handle_duplicate_item_activated)
        self.__duplicate_item.show()

        self.__close_item = gtk.ImageMenuItem.new_from_stock(gtk.STOCK_CLOSE)
        self.__close_item.connect("activate", self.__handle_close_item_activated)
        self.__close_item.show()

        self.__tab_label_menu = gtk.Menu()
        self.__tab_label_menu.append(self.__properties_item)
        self.__tab_label_menu.append(self.__duplicate_item)
        self.__tab_label_menu.append(self.__close_item)

        self.__tab_icon = gtk.Image.new_from_pixbuf(self.__icons[self.__icon_name])
        self.__tab_icon.show()

        self.__tab_title = gtk.Label.new(self.__title)
        self.__tab_title.show()

        tab_layout = gtk.Box.new(gtk.Orientation.HORIZONTAL, 4)
        tab_layout.pack_start(self.__tab_icon, False, True, 0)
        tab_layout.pack_start(self.__tab_title, True, True, 0)
        tab_layout.show()

        self.__tab_label = gtk.EventBox.new()
        self.__tab_label.add(tab_layout)
        self.__tab_label.connect("button-press-event", self.__handle_tab_label_button_press)
        self.__tab_label.show()

        self.__copy_item = gtk.MenuItem.new_with_label("Copy")
        self.__copy_item.connect("activate", self.__handle_copy_item_activated)
        self.__copy_item.show()

        self.__paste_item = gtk.MenuItem.new_with_label("Paste")
        self.__paste_item.connect("activate", self.__handle_paste_item_activated)
        self.__paste_item.show()

        self.__copy_and_paste_item = gtk.MenuItem.new_with_label("Copy and paste")
        self.__copy_and_paste_item.connect("activate", self.__handle_copy_and_paste_item_activated)
        self.__copy_and_paste_item.show()

        self.__insert_password_item = gtk.MenuItem.new_with_label("Insert password")
        self.__insert_password_item.connect("activate", self.__handle_insert_password_item_activated)
        self.__insert_password_item.show()

        self.__terminal_menu = gtk.Menu.new()
        self.__terminal_menu.append(self.__copy_item)
        self.__terminal_menu.append(self.__paste_item)
        self.__terminal_menu.append(self.__copy_and_paste_item)
        self.__terminal_menu.append(self.__insert_password_item)

        self.__terminal = vte.Terminal()
        self.__terminal.set_events(gdk.EventMask.KEY_PRESS_MASK | gdk.EventMask.BUTTON_PRESS_MASK)
        self.__terminal.set_audible_bell(True)
        self.__terminal.set_allow_bold(True)
        self.__terminal.set_scroll_on_output(False)
        self.__terminal.set_scroll_on_keystroke(True)
        self.__terminal.set_rewrap_on_resize(True)
        self.__terminal.set_colors(gdk.RGBA(0.75, 0.75, 0.75), gdk.RGBA(0, 0, 0), self.__COLOR_PALETTE) # Do this before configuring the cursor's color
        self.__terminal.set_cursor_shape(vte.CursorShape.BLOCK)
        self.__terminal.set_cursor_blink_mode(vte.CursorBlinkMode.ON)
        self.__terminal.set_color_cursor(gdk.RGBA(1, 0, 0))
        self.__terminal.set_color_highlight(gdk.RGBA(0, 0, 1))
        self.__terminal.set_color_highlight_foreground(gdk.RGBA(1, 1, 1))
        self.__terminal.set_scrollback_lines(-1)
        self.__terminal.connect("child-exited", self.__handle_terminal_child_exited)
        self.__terminal.connect("key-press-event", self.__handle_terminal_key_press_event)
        self.__terminal.connect("contents-changed", self.__handle_terminal_contents_changed)
        self.__terminal.connect("selection-changed", self.__handle_terminal_selection_changed)
        self.__terminal.connect("button-press-event", self.__handle_terminal_button_press)
        self.__terminal.connect("current-directory-uri-changed", self.__handle_terminal_directory_changed)
        self.__terminal.show()

        self.__password_entry = gtk.Entry.new()
        self.__password_entry.set_visibility(False)
        self.__password_entry.connect("activate", self.__handle_password_entry_activated)
        self.__password_entry.show()

        self.__password_dialog = gtk.Dialog(
            "Password",
            self.__window,
            gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            (gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL, gtk.STOCK_OK, gtk.ResponseType.OK))
        self.__password_dialog.get_content_area().pack_start(self.__password_entry, True, True, 0)

        self.add(self.__terminal)
        self.connect("map", self.__handle_map)

        self.__child_process = self.__terminal.spawn_sync(
            vte.PtyFlags.DEFAULT, # PTY flags
            self.__initial_working_dir, # Working directory
            self.__command, # Argv
            [], # Envv
            glib.SpawnFlags.DEFAULT, # Spawn flags
            None, # Child setup
            None, # Child setup data
            None) # Cancellable
        self.__terminal.watch_child(self.__child_process.child_pid)

    def get_tab_label(self):
        return self.__tab_label

    def get_properties(self):
        return self.__title, self.__notifications_enabled, self.__icon_name, self.__command, self.__get_working_dir()

    def __get_working_dir(self):
        working_dir_uri = self.__terminal.get_current_directory_uri()

        if working_dir_uri is None:
            return self.__initial_working_dir

        return urllib.parse.unquote(urllib.parse.urlparse(working_dir_uri).path)

    def __handle_notification_timeout_expiry(self):
        assert self.__notification_timeout is not None
        self.__tab_title.set_markup(f"<span weight=\"bold\" color=\"red\">{html.escape(self.__title)}</span>")
        self.__notification.update(self.__title, f"New input was received in tab '{self.__title:s}'.", "dialog-information")
        self.__notification.show()
        self.__notification_timeout = None
        return False

    def __handle_tab_label_button_press(self, tab_label, event):
        assert self.__tab_label is tab_label

        if event.type == gdk.EventType.BUTTON_PRESS:
            if event.button == gdk.BUTTON_SECONDARY:
                self.__tab_label_menu.popup_at_pointer()
                return True

        return False

    def __handle_map(self, widget):
        assert self is widget

        if self.__notification_timeout is not None:
            glib.source_remove(self.__notification_timeout)
            self.__notification_timeout = None

        self.__tab_title.set_text(self.__title)
        self.__notification.close()

    def __handle_properties_item_activated(self, properties_item):
        assert self.__properties_item is properties_item

        title_entry = gtk.Entry()
        title_entry.set_text(self.__title)
        title_entry.show()

        notifications_checkbox = gtk.CheckButton.new_with_label("Show notifications")
        notifications_checkbox.set_active(self.__notifications_enabled)
        notifications_checkbox.show()

        icon_model = gtk.ListStore(str, pixbuf.Pixbuf)
        for name, icon in sorted(self.__icons.items()):
            icon_model.append((name, icon))

        icon_view = gtk.IconView(icon_model)
        icon_view.set_text_column(0)
        icon_view.set_pixbuf_column(1)
        icon_view.set_selection_mode(gtk.SelectionMode.SINGLE)
        icon_view.show()

        scrollbars = gtk.ScrolledWindow()
        scrollbars.set_size_request(800, 600)
        scrollbars.add(icon_view)
        scrollbars.show()

        layout = gtk.VBox(False, 4)
        layout.pack_start(title_entry, False, True, 0)
        layout.pack_start(notifications_checkbox, False, True, 0)
        layout.pack_start(scrollbars, False, True, 0)
        layout.show()

        dialog = gtk.Dialog(
            f"Change label of tab '{self.__title}'",
            self.__window,
            gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            (gtk.STOCK_CANCEL, gtk.ResponseType.CANCEL, gtk.STOCK_OK, gtk.ResponseType.OK))
        dialog.get_content_area().pack_start(layout, True, True, 0)

        if dialog.run() == gtk.ResponseType.OK:
            self.__title = title_entry.get_text()
            self.__notifications_enabled = notifications_checkbox.get_active()
            self.__tab_title.set_text(self.__title)

            selected_icon = icon_view.get_selected_items()
            if selected_icon:
                self.__icon_name, icon = icon_model[selected_icon[0]]
                self.__tab_icon.set_from_pixbuf(icon)

            self.emit("changed")

        dialog.destroy()
        return True

    def __handle_duplicate_item_activated(self, duplicate_item):
        assert self.__duplicate_item is duplicate_item

        self.emit("duplicated", self.__title, self.__notifications_enabled, self.__icon_name, self.__command, self.__get_working_dir())

    def __handle_close_item_activated(self, close_item):
        assert self.__close_item is close_item

        dialog = gtk.MessageDialog(
            self.__window,
            gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            gtk.MessageType.QUESTION,
            gtk.ButtonsType.OK_CANCEL,
            f"Close tab '{self.__title}'?")

        if dialog.run() == gtk.ResponseType.OK:
            self.emit("closed")

        dialog.destroy()
        return True

    def __handle_terminal_child_exited(self, terminal, exit_status):
        assert self.__terminal is terminal
        self.emit("closed")

    def __handle_terminal_key_press_event(self, terminal, event):
        assert self.__terminal is terminal

        masked_state = event.state & (gdk.ModifierType.CONTROL_MASK | gdk.ModifierType.SHIFT_MASK | gdk.ModifierType.META_MASK | gdk.ModifierType.SUPER_MASK | gdk.ModifierType.HYPER_MASK)
        snippet      = self.__snippets.get((event.keyval, masked_state))

        if snippet is not None:
            variables = {
                "HOME": os.path.expanduser("~"),
                "PWD":  self.__get_working_dir()}

            self.__terminal.feed_child(tuple(map(ord, "".join(map(lambda part: part(lambda variable: variables.get(variable, "")), snippet)))))
            return True

        return False

    def __handle_terminal_contents_changed(self, terminal):
        assert self.__terminal is terminal

        if self.__notifications_enabled and not self.get_mapped():
            if self.__notification_timeout is not None:
                glib.source_remove(self.__notification_timeout)

            self.__notification_timeout = glib.timeout_add(self.__NOTIFICATION_TRIGGER_TIME, self.__handle_notification_timeout_expiry)
            self.__tab_title.set_markup(f"<span weight=\"bold\" style=\"italic\" color=\"magenta\">{html.escape(self.__title)}</span>")

    def __handle_terminal_selection_changed(self, terminal):
        assert self.__terminal is terminal

        if self.__terminal.get_has_selection():
            self.__terminal.copy_primary()

    def __handle_terminal_button_press(self, terminal, event):
        assert self.__terminal is terminal

        if event.type == gdk.EventType.BUTTON_PRESS:
            if event.button == gdk.BUTTON_SECONDARY:
                self.__terminal_menu.popup_at_pointer()
                return True

            if event.button == gdk.BUTTON_MIDDLE:
                self.__terminal.paste_primary()
                return True

        return False

    def __handle_terminal_directory_changed(self, terminal):
        self.emit("changed")

    def __handle_copy_item_activated(self, copy_item):
        assert self.__copy_item is copy_item
        self.__terminal.copy_clipboard()

    def __handle_paste_item_activated(self, paste_item):
        assert self.__paste_item is paste_item
        self.__terminal.paste_clipboard()

    def __handle_copy_and_paste_item_activated(self, copy_and_paste_item):
        assert self.__copy_and_paste_item is copy_and_paste_item
        self.__terminal.copy_clipboard()
        self.__terminal.paste_clipboard()

    def __generate_password_menu(self, group):
        menu = gtk.Menu.new()
        menu.show()

        for subgroup in group.subgroups:
            item = gtk.MenuItem.new_with_label(subgroup.name)
            item.set_submenu(self.__generate_password_menu(subgroup))
            item.show()

            menu.append(item)

        for entry in group.entries:
            item = gtk.MenuItem.new_with_label(entry.title)
            item.connect("activate", self.__enter_password(entry.password))
            item.show()

            menu.append(item)

        return menu

    def __enter_password(self, password):
        def closure(item):
            self.__terminal.feed_child(tuple(map(ord, password)))

        return closure

    def __handle_insert_password_item_activated(self, insert_password_item):
        assert self.__insert_password_item is insert_password_item

        while True:
            if self.__stored_password is None:
                try:
                    if self.__password_dialog.run() != gtk.ResponseType.OK:
                        break
                finally:
                    self.__password_dialog.hide()

                self.__stored_password = self.__password_entry.get_text()

            try:
                with pykeepass.PyKeePass("/home/bartsas/Documents/Passwords.kdbx", password=self.__stored_password) as password_database:
                    password_menu = self.__generate_password_menu(password_database.root_group)

                password_menu.popup_at_pointer()
                break
            except Exception as exception:
                self.__stored_password = None

    def __handle_password_entry_activated(self, entry):
        assert self.__password_entry is entry
        self.__password_dialog.response(gtk.ResponseType.OK)

class Application:
    __ICON_DIRECTORY         = "~/.terminal/icons"
    __SNIPPETS_CONFIGURATION = "~/.terminal/snippets.ini"
    __COMMANDS_CONFIGURATION = "~/.terminal/commands.ini"
    __TABS_CONFIGURATION     = "~/.terminal/tabs.csv"

    def __init__(self):
        glib.set_prgname("My Terminal")
        glib.set_application_name("My Terminal")

        self.__application = gtk.Application.new("com.accelleran.terminal", gio.ApplicationFlags.HANDLES_OPEN)
        self.__application.connect("startup", self.__handle_application_startup_event)
        self.__application.connect("activate", self.__handle_application_activate_event)
        self.__application.connect("open", self.__handle_application_open_event)
        self.__application.run(sys.argv)

    def __handle_application_startup_event(self, application):
        assert application is self.__application

        notify.init("My Terminal")

        icon_directory = os.path.expanduser(self.__ICON_DIRECTORY)
        self.__icons = {os.path.splitext(icon_file.name)[0]: pixbuf.Pixbuf.new_from_file(icon_file.path) for icon_file in os.scandir(icon_directory)}

        snippets_configuration = configparser.ConfigParser(interpolation=None)
        snippets_configuration.read(os.path.expanduser(self.__SNIPPETS_CONFIGURATION))
        self.__snippets = {gtk.accelerator_parse(title): compile_snippet(section["Snippet"]) for title, section in snippets_configuration.items() if title != snippets_configuration.default_section}

        commands_configuration = configparser.ConfigParser(interpolation=None)
        commands_configuration.read(os.path.expanduser(self.__COMMANDS_CONFIGURATION))

        start_menu = gtk.Menu()
        open_at_startup = []

        for title, section in commands_configuration.items():
            if title != commands_configuration.default_section:
                icon_name   = section["Icon"]
                command     = shlex.split(section["Command"])
                working_dir = os.path.expanduser(section.get("Working Dir", "~"))

                if section.getboolean("Open at Startup", False):
                    open_at_startup.append((title, icon_name, command, working_dir))

                item_icon = gtk.Image.new_from_pixbuf(self.__icons[icon_name])
                item_icon.show()

                start_item = gtk.ImageMenuItem.new_with_label(title)
                start_item.set_always_show_image(True)
                start_item.set_image(item_icon)
                start_item.connect("activate", self.__handle_start_item_activated, title, icon_name, command, working_dir)
                start_item.show()

                start_menu.append(start_item)

        start_icon = gtk.Image.new_from_icon_name("tab-new", gtk.IconSize.BUTTON)
        start_icon.show()

        self.__start_button = gtk.MenuButton()
        self.__start_button.set_label("\u2001\u2001New Terminal\u2001\u2001")
        self.__start_button.set_always_show_image(True)
        self.__start_button.set_image(start_icon)
        self.__start_button.set_popup(start_menu)
        self.__start_button.show()

        self.__notebook = gtk.Notebook()
        self.__notebook.set_tab_pos(gtk.PositionType.LEFT)
        self.__notebook.set_scrollable(True)
        self.__notebook.set_action_widget(self.__start_button, gtk.PackType.END)
        self.__notebook.show()

        self.__window = gtk.ApplicationWindow.new(self.__application)
        self.__window.set_title("My Terminal")
        self.__window.set_icon_name("terminal")
        self.__window.set_wmclass("my-terminal", "My Terminal")
        self.__window.add(self.__notebook)
        self.__window.maximize()
        self.__window.connect("delete-event", self.__handle_window_deleted)
        self.__window.show()

        with open(os.path.expanduser(self.__TABS_CONFIGURATION), newline="") as tabs_configuration:
            for title, notifications_enabled, icon_name, command, working_dir in csv.reader(tabs_configuration):
                self.__create_terminal(title, notifications_enabled.lower() == "true", icon_name, shlex.split(command), working_dir)

        if self.__notebook.get_n_pages() == 0:
            for title, icon_name, command, terminal in open_at_startup:
                self.__create_terminal(title, True, icon_name, command, terminal)

    def __handle_application_activate_event(self, application):
        assert application is self.__application

        self.__window.present()

    def __handle_application_open_event(self, application, files_to_open, hint, user_data):
        assert application is self.__application

        for file_to_open in files_to_open:
            directory_path = file_to_open
            while directory_path is not None:
                if directory_path.query_info(gio.FILE_ATTRIBUTE_STANDARD_TYPE, gio.FileQueryInfoFlags.NONE, None).get_file_type() == gio.FileType.DIRECTORY:
                    self.__create_terminal(file_to_open.get_basename(), True, "Blue Folder", ["/usr/bin/fish"], directory_path.get_path()) # TODO make configurable
                    break
                directory_path = directory_path.get_parent()

        self.__window.present()

    def __save_tabs(self):
        with open(os.path.expanduser(self.__TABS_CONFIGURATION), "w") as tabs_configuration:
            writer = csv.writer(tabs_configuration)
            tab_count = self.__notebook.get_n_pages()

            for tab_index in range(tab_count):
                terminal = self.__notebook.get_nth_page(tab_index)
                title, notifications_enabled, icon_name, command, working_dir = terminal.get_properties()
                writer.writerow((title, "true" if notifications_enabled else "false", icon_name, " ".join(map(shlex.quote, command)), working_dir))

    def __close_application(self):
        self.__save_tabs()
        self.__application.quit()

    def __create_terminal(self, title, notifications_enabled, icon_name, command, working_dir):
        terminal = Terminal(self.__window, self.__icons, self.__snippets, title, notifications_enabled, icon_name, command, working_dir)
        terminal.connect("changed", self.__handle_terminal_changed)
        terminal.connect("duplicated", self.__handle_terminal_duplicated)
        terminal.connect("closed", self.__handle_terminal_closed)
        terminal.show()

        self.__notebook.set_current_page(self.__notebook.append_page(terminal, terminal.get_tab_label()))
        self.__notebook.set_tab_reorderable(terminal, True)
        self.__save_tabs()

    def __handle_start_item_activated(self, start_item, title, icon_name, command, working_dir):
        self.__create_terminal(title, True, icon_name, command, working_dir)

    def __handle_terminal_changed(self, terminal):
        self.__save_tabs()

    def __handle_terminal_duplicated(self, terminal, title, notifications_enabled, icon_name, command, working_dir):
        self.__create_terminal(title, notifications_enabled, icon_name, command, working_dir)

    def __handle_terminal_closed(self, terminal):
        self.__notebook.remove_page(self.__notebook.page_num(terminal))

        if self.__notebook.get_n_pages() == 0:
            self.__close_application()
        else:
            self.__save_tabs()

    def __handle_window_deleted(self, window, event):
        assert self.__window is window

        dialog = gtk.MessageDialog(
            self.__window,
            gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            gtk.MessageType.QUESTION,
            gtk.ButtonsType.OK_CANCEL,
            "Close terminal?")

        if dialog.run() == gtk.ResponseType.OK:
            self.__close_application()

        dialog.destroy()
        return True

Application()
