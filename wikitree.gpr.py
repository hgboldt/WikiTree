# File: wikitree.gpr.py
register(GRAMPLET,
         id="WikiTree",
         name=_("WikiTree"),
         description = _("WikiTree Integration"),
         version="0.1.0",
         gramps_target_version="5.1",
         status = STABLE,
         fname="wikitree.py",
         height = 50,
         detached_width = 400,
         detached_height = 500,
         gramplet = 'WikiTree',
         gramplet_title=_("WikiTree"),
         help_url="5.1_Addons#Addon_List",
         navtypes=['Person']
         )
