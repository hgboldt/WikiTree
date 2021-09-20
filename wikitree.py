# WikiTree - WikiTree Integration
#
# Copyright (C) 2021  Hans Boldt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

#-------------------#
# Python modules    #
#-------------------#
from html import escape
from datetime import datetime
import json
import requests
import sys

import pdb

#------------------#
# Gtk modules      #
#------------------#
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

try:
    gi.require_version('WebKit2', '4.0')
    from gi.repository import WebKit2

    import mwparserfromhell
    import mwcomposerfromhell
except:
    pass


#-------------------#
# Gramps modules    #
#-------------------#
from gramps.gen.plug import Gramplet
from gramps.gen.lib import (Person, ChildRefType, EventType,
                            Attribute, AttributeType, EventRoleType)
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.datehandler import get_date
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.utils.db import (get_birth_or_fallback,
                                 get_death_or_fallback,
                                 get_participant_from_event)
from gramps.gen.config import config
from gramps.gen.utils.symbols import Symbols
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn


# Other gramplet modules
from biowindow import BioWindow
from services import (format_name, format_person_info, format_date,
                      get_wikitree_attributes,
                      get_wikitree_attributes_from_handle,
                      save_wikitree_id_to_person)


have_cosanguinuity = False
try:
    from cosanguinuity import Pedigree
    have_cosanguinuity = True
except Exception as e:
    pass

#------------------#
# Translation      #
#------------------#
try:
    _trans = glocale.get_addon_translator(__file__)
    _ = _trans.gettext
except ValueError:
    _ = glocale.translation.sgettext
ngettext = glocale.translation.ngettext # else "nearby" comments are ignored




SEARCH_LIMIT = 25



#====================================================
#
# Class WikiTreeGramplet
#
#====================================================

class WikiTree(Gramplet):

    def init(self):
        self.active_label = None
        self.id_entry = None

        self.gui.WIDGET = self.build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)


    def db_changed(self):
        self.connect(self.dbstate.db, 'person-add', self.update)
        self.connect(self.dbstate.db, 'person-delete', self.update)
        self.connect(self.dbstate.db, 'person-update', self.update)


    def active_changed(self, handle):
        self.update()


    def build_gui(self):
        """
        Build the GUI interface.
        """
        grid = Gtk.Grid()
        grid.set_border_width(6)
        grid.set_row_spacing(6)
        grid.set_column_spacing(20)

        # Name
        self.active_label = Gtk.Label(label='')
        grid.attach(self.active_label, 0, 0, 2, 1)

        # Id entry and buttons
        id_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        id_label = Gtk.Label(label=_("Id:"))
        id_box.pack_start(id_label, \
                          expand=False, fill=False, padding=5)

        self.id_entry = Gtk.Entry()
        self.id_entry.connect("focus-out-event", self.id_updated)
        id_box.pack_start(self.id_entry, \
                          expand=False, fill=False, padding=5)

        update_id_button = Gtk.Button.new_with_label(_("Update Id"))
        update_id_button.connect('clicked', self.on_click_update_id)
        id_box.pack_start(update_id_button, \
                          expand=False, fill=False, padding=5)

        grid.attach(id_box, 0, 1, 2, 1)

        # Search box and options
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        search_button = Gtk.Button.new_with_label(_("Search"))
        search_button.connect("clicked", self.on_click_search)
        search_box.pack_start(search_button, \
                                expand=False, fill=False, padding=0)

        self.use_dob_button \
                = Gtk.CheckButton(label = _('Include date of birth in search'))
        self.use_dob_button.set_active(True)
        search_box.pack_start(self.use_dob_button, \
                                expand=False, fill=False, padding=0)

        self.use_dod_button \
                = Gtk.CheckButton(label = _('Include date of death in search'))
        self.use_dod_button.set_active(True)
        search_box.pack_start(self.use_dod_button, \
                                expand=False, fill=False, padding=0)

        grid.attach(search_box, 0, 2, 1, 1)

        # View box
        view_button = Gtk.Button.new_with_label(_("View"))
        view_button.connect("clicked", self.on_click_view)
        grid.attach(view_button, 0, 3, 1, 1)

        # Generate bio button and options
        generate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        generate_button = Gtk.Button.new_with_label(_("Generate Bio"))
        generate_button.connect("clicked", self.on_click_generate)
        generate_box.pack_start(generate_button, \
                                expand=False, fill=False, padding=0)

        self.include_witness_events_button \
                = Gtk.CheckButton(label = _('Include witness events'))
        self.include_witness_events_button.set_active(True)
        generate_box.pack_start(self.include_witness_events_button, \
                                expand=False, fill=False, padding=0)

        self.include_witnesses_button \
                = Gtk.CheckButton(label = _('Include witnesses'))
        self.include_witnesses_button.set_active(True)
        generate_box.pack_start(self.include_witnesses_button, \
                                expand=False, fill=False, padding=0)

        self.include_notes_button \
                = Gtk.CheckButton(label = _('Include notes'))
        self.include_notes_button.set_active(True)
        generate_box.pack_start(self.include_notes_button, \
                                expand=False, fill=False, padding=0)

        if have_cosanguinuity:
            self.include_pedigree_collapse_button \
                    = Gtk.CheckButton(label = _('Include pedigree collapse section'))
            self.include_pedigree_collapse_button.set_active(False)
            generate_box.pack_start(self.include_pedigree_collapse_button, \
                                    expand=False, fill=False, padding=0)

        grid.attach(generate_box, 0, 4, 1, 1)

        grid.show_all()
        return grid


    def id_updated(self, a, b):
        return


    def on_click_search(self, arg):
        self.uistate.set_busy_cursor(True)
        db = self.dbstate.db
        active_handle = self.get_active('Person')
        details = dict()

        person = db.get_person_from_handle(active_handle)
        primary_name = person.get_primary_name()
        surname = primary_name.get_primary_surname()
        details['limit'] = SEARCH_LIMIT
        details['LastName'] = surname.get_prefix() + ' ' + surname.get_surname()
        details['FirstName'] = primary_name.get_first_name()

        gender = person.get_gender()
        if gender == Person.MALE:
            details['Gender'] = 'Male'
        elif gender == Person.FEMALE:
            details['Gender'] = 'Female'

        if self.use_dob_button.get_active():
            bdate = get_birth_or_fallback(db, person)
            if bdate and bdate.get_type() == EventType.BIRTH:
                bd = get_date(bdate)
                if len(bd) == 10:
                    details['BirthDate'] = bd

        if self.use_dod_button.get_active():
            ddate = get_death_or_fallback(db, person)
            if ddate and ddate.get_type() == EventType.DEATH:
                dd = get_date(ddate)
                if len(dd) == 10:
                    details['DeathDate'] = dd

        search_win = SearchWindow(details, db, person)
        self.uistate.set_busy_cursor(False)
        return


    def on_click_view(self, arg):
        self.uistate.set_busy_cursor(True)
        db = self.dbstate.db
        active_handle = self.get_active('Person')
        person = db.get_person_from_handle(active_handle)
        wikitree_attr = get_wikitree_attributes(db, person)
        if not wikitree_attr:
            return

        view_win = ViewWindow(wikitree_attr['id'], db, person)
        self.uistate.set_busy_cursor(False)
        return


    def on_click_generate(self, arg):
        self.uistate.set_busy_cursor(True)
        db = self.dbstate.db
        active_handle = self.get_active('Person')
        person = db.get_person_from_handle(active_handle)
        bio_win = BioWindow(db, person, \
                            self.include_witness_events_button.get_active(), \
                            self.include_witnesses_button.get_active(), \
                            self.include_notes_button.get_active() )
        self.uistate.set_busy_cursor(False)
        return


    def on_click_update_id(self, arg):
        self.uistate.set_busy_cursor(True)
        db = self.dbstate.db
        active_handle = self.get_active('Person')
        person = db.get_person_from_handle(active_handle)
        save_wikitree_id_to_person(db, person, self.id_entry.get_text())
        self.uistate.set_busy_cursor(False)


    def main(self):

        db = self.dbstate.db
        active_handle = self.get_active('Person')
        if not active_handle:
            return

        self.active_handle = active_handle
        person = db.get_person_from_handle(active_handle)
        name = name_displayer.display_name(person.get_primary_name())
        self.active_label.set_markup('<b>' + name + '</b>')

        # Do we have a WikiTree id?
        wikitree_attr = get_wikitree_attributes(db, person)
        if wikitree_attr:
            self.id_entry.set_text(wikitree_attr['id'])
        else:
            self.id_entry.set_text('')



#====================================================
#
# Class ViewWindow
#
#====================================================

class ViewWindow(Gtk.Window):
    """
    Window showing WikiTree information for a person
    """

    def __init__(self, wikitree_id, db, active_person):
        """
        Initialize window
        """
        self.db = db
        self.active_person = active_person

        # Do we have all the necessary Python packages?
        self.html_ok = False
        try:
            x = mwcomposerfromhell
            self.html_ok = True
        except NameError:
            pass

        Gtk.Window.__init__(self, title=_("WikiTree Browser"))
        self.set_default_size(800, 800)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.homogenous = False
        box.set_border_width(10)

        # Entry
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        entry_box.homogenous = False
        entry_label = Gtk.Label(_('WikiTree Id: '))
        entry_box.pack_start(entry_label, expand=False, fill=False, padding=0)
        self.entry_entry = Gtk.Entry()
        self.entry_entry.set_text(wikitree_id)
        self.entry_entry.connect('activate', self.on_click_go)
        entry_box.pack_start(self.entry_entry, expand=False, fill=False, padding=0)
        entry_button = Gtk.Button.new_with_label(_('Go!'))
        entry_button.connect('clicked', self.on_click_go)
        entry_box.pack_start(entry_button, expand=False, fill=False, padding=0)
        entry_save_button = Gtk.Button.new_with_label(_('Save Id to Active Person'))
        entry_save_button.connect('clicked', self.on_click_save_id)
        entry_box.pack_start(entry_save_button, expand=False, fill=False, padding=0)
        box.pack_start(entry_box, expand=False, fill=False, padding=5)

        # Information
        self.info_label = Gtk.Label(label='')
        self.info_label.set_xalign(0)
        self.info_label.connect('activate_link', self.link_handler)
        box.pack_start(self.info_label, expand=False, fill=False, padding=5)

        # Biography
        bio_notebook = Gtk.Notebook()

        if self.html_ok:
            html_window = Gtk.ScrolledWindow()
            self.html_window = WebKit2.WebView()
            html_window.add(self.html_window)
            bio_notebook.append_page(html_window, Gtk.Label(label=_("Formatted")))

        bio_window = Gtk.ScrolledWindow()
        self.bio_label = Gtk.Label(label='')
        self.bio_label.set_yalign(0)
        self.bio_label.set_xalign(0)
        bio_window.add(self.bio_label)
        bio_notebook.append_page(bio_window, Gtk.Label(label=_("WikiCode")))

        box.pack_start(bio_notebook, expand=True, fill=True, padding=0)

        self.add(box)
        box.show_all()
        self.show_all()
        if wikitree_id:
            self.fill_data(wikitree_id)


    def on_click_go(self, button):
        """
        """
        id = self.entry_entry.get_text()
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.fill_data, id)
        return True


    def on_click_save_id(self, button):
        """
        """
        id = self.entry_entry.get_text()
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.do_click_save_id, id)
        return True


    def do_click_save_id(self, id):
        """
        """
        save_wikitree_id_to_person(self.db, self.active_person, id)


    def link_handler(self, label, uri):
        """
        """
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.fill_data, uri)
        return True


    def fill_data(self, wikitree_id):
        """
        Get and format data for a person
        """
        # Get profile information
        url = 'https://api.wikitree.com/api.php'
        data = {'action': 'getRelatives',
                'keys': wikitree_id,
                'getParents': '1',
                'getSpouses': '1',
                'getChildren': '1',
                'getSiblings': '0',
                'format': 'json'}
        profile = requests.post(url, data)
        info_text = self.format_info(profile)
        self.info_label.set_markup(info_text)

        # Get bio information
        data = {'action': 'getBio',
                'key': wikitree_id,
                'bioFormat': 'both'}
        bio = requests.post(url,data)
        bio_text = self.format_bio(bio)

        self.bio_label.set_text(bio_text)

        if self.html_ok:
            wikicode = mwparserfromhell.parse(bio_text)
            html = mwcomposerfromhell.compose(wikicode)
            self.html_window.load_html(html, None)

        self.entry_entry.set_text(wikitree_id)


    def format_info(self, response):
        """
        Format basic information about a person.
        """
        profile = json.loads(response.content)[0]['items'][0]
        prof = profile['person']

        # Basic information about person
        text = format_person_info(prof)

        # Extract parents
        fatherx = str(prof['Father'])
        if fatherx and fatherx != '0' and fatherx != 'None':
            father = prof['Parents'][fatherx]
            text += '<b>Father:</b> ' + format_name(father) + "\n"
        motherx = str(prof['Mother'])
        # pdb.set_trace()
        if motherx and motherx != '0' and motherx != 'None':
            mother = prof['Parents'][motherx]
            text += '<b>Mother:</b> ' + format_name(mother) + "\n"

        # Extract spouses and children
        spouses = prof['Spouses'] if 'Spouses' in prof else None
        children = prof['Children'] if 'Children' in prof else None
        if spouses:
            for sp in spouses:
                spouse = spouses[sp]
                text += '<b>Spouse/Children:</b> ' + format_name(spouse) + "\n"
                # Print out children:
                for ch in children:
                    child = children[ch]
                    if spouse['Id'] == child['Father'] or spouse['Id'] == child['Mother']:
                        text += "\t" + format_name(child) + "\n"
        elif children:
            # Print out children:
            text += "<b>Children:</b>\n"
            for ch in children:
                child = children[ch]
                text += "\t" + format_name(child) + "\n"

        text += "\n<b>Biography:</b>\n"
        return text


    def format_bio(self, response):
        """
        Format the biography information.
        """
        bio = json.loads(response.content)[0]
        text = bio['bio'] if 'bio' in bio else ''
        return text


#====================================================
#
# Class SearchWindow
#
#====================================================

class SearchWindow(Gtk.Window):
    """
    """

    def __init__(self, search_details, db, active_person):
        """
        """
        self.db = db
        self.active_person = active_person

        Gtk.Window.__init__(self, title=_("WikiTree Search Results"))
        self.set_default_size(800, 800)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.homogenous = False
        box.set_border_width(10)

        # Search parameters
        args = ''
        for d in search_details:
            detail = search_details[d]
            args += "<b>%s:</b> %s\n" % (self._fix_name(d), search_details[d])
        args_label = Gtk.Label()
        args_label.set_markup(args)
        args_label.set_xalign(0)
        box.pack_start(args_label, expand=False, fill=False, padding=0)

        # Search results
        results_window = Gtk.ScrolledWindow()

        self.results_grid = Gtk.Grid()
        self.results_grid.set_border_width(6)
        self.results_grid.set_row_spacing(6)
        self.results_grid.set_column_spacing(20)
        results_window.add(self.results_grid)
        box.pack_start(results_window, expand=True, fill=True, padding=5)

        self.add(box)
        box.show_all()
        self.show_all()

        # Fill search results
        self.search(search_details)
        return


    def _fix_name(self, name):
        """
        """
        result = ''
        for c in name:
            if result and c.isupper():
                result += ' ' + c
            else:
                result += c
        return result


    def search(self, search_details):
        """
        """
        url = 'https://api.wikitree.com/api.php'
        data = dict(search_details)
        data['action'] = 'searchPerson'
        results = requests.post(url, data)
        if results:
            results = json.loads(results.content)

        # Print out results
        text = ''
        line = 0
        for match in results[0]['matches']:
            if 'LongNamePrivate' in match:
                lab = Gtk.Label(label='')
                lab.set_markup(format_person_info(match, show_id=True))
                lab.set_xalign(0)
                lab.connect('activate_link', self.link_handler)
                self.results_grid.attach(lab, 0, line, 1, 1)

                # butt = Gtk.Button.new_with_label('Save Id to Active Person')
                butt = ButtonWithValues()
                butt.set_label('Save Id to Active Person')
                butt.set_value('id', match['Name'])
                butt.connect('clicked', self.on_click_save_id)
                self.results_grid.attach(butt, 1, line, 1, 1)

                line += 1

        if line == 0:
            lab = Gtk.Label(label='')
            lab.set_markup(_("<b>No matches found</b>\n"))
            lab.set_xalign(0)
            self.results_grid.attach(lab, 0, line, 1, 1)

        self.results_grid.show_all()


    def link_handler(self, label, uri):
        """
        """
        Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.link_show_view, uri)
        return True


    def link_show_view(self, id):
        """
        """
        view_win = ViewWindow(id, self.db, self.active_person)


    def on_click_save_id(self, button):
        id = button.get_value('id')
        self.do_click_save_id(id)
        return True


    def do_click_save_id(self, id):
        """
        """
        save_wikitree_id_to_person(self.db, self.active_person, id)


#====================================================
#
# Class ButtonWithValues
#
#====================================================

class ButtonWithValues(Gtk.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.values = {}

    def set_value(self, key, value):
        self.values[key] = value

    def get_value(self, key):
        if key in self.values:
            return self.values[key]
        return None



