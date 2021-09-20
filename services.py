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



from html import escape
import json



def format_name(person):
    """
    Format the name with a clickable link.
    """
    if 'LongName' in person:
        longname = person['LongName']
    else:
        longname = person['LongNamePrivate']

    return "<a href=\"%s\">%s</a>" % (person['Name'], longname)


def format_person_info(person, show_id=False):
    """
    Output an information string for the person.
    """
    id_text = (' [' + person['Name'] + ']') if show_id else ''

    text = "<b>Name:</b> " + format_name(person) + id_text + "\n"
    text += '<b>Date/place of birth:</b> ' \
            + (person['BirthDate'] if 'BirthDate' in person else '------') + ', ' \
            + ((person['BirthLocation'] if 'BirthLocation' in person else '') or '')  + "\n"
    text += '<b>Date/place of death:</b> ' \
            + (person['DeathDate'] if 'DeathDate' in person else '------') + ', ' \
            + ((person['DeathLocation'] if 'DeathLocation' in person else '') or '')  + "\n"
    return text


def format_date(date, preferred_event_type, alt_event_type):
    """
    Format the given date.
    """
    if not date:
        return ''
    sdate = get_date(date)
    if not sdate:
        return ''
    sdate = escape(sdate)
    date_type = date.get_type()
    if preferred_event_type == EventType.BIRTH:
        if date_type != preferred_event_type:
            return "<i>%s</i>" % (sdate)
        return "%s" % (sdate)
    else:
        if date_type != preferred_event_type:
            return "<i>%s</i>" % (sdate)
        return "%s" % (sdate)

    return sdate


def get_wikitree_attributes(db, person):
    """
    Get the WikiTree attributes for the specified person
    """
    attr_list = person.get_attribute_list()
    for attr in attr_list:
        if attr.get_type() == 'WikiTree':
            return json.loads(attr.get_value())
    return None


def get_wikitree_attributes_from_handle(db, person_handle):
    """
    Get the WikiTree attributes for the specified person
    """
    person = db.get_person_from_handle(person_handle)
    return get_wikitree_attributes(db, person)



def save_wikitree_id_to_person(db, person, id):
    """
    Save WikiTree id to specified person
    """
    attrs = person.get_attribute_list()

    with DbTxn("WikiTree Marker", db) as transaction:
        wtattr = None
        for attr in attrs:
            if attr.type.value == 'WikiTree':
                wtattr = json.loads(attr.get_value())
                wtattr['id'] = id
                attr.set_value(json.dumps(wtattr))
                break

        if not wtattr:
            wtattr = {'id': id, 'owner': 0}
            jsattr = json.dumps(wtattr)
            attr = Attribute()
            attr.set_type((AttributeType.CUSTOM, 'WikiTree'))
            attr.set_value(jsattr)
            person.add_attribute(attr)

        db.commit_person(person, transaction)
