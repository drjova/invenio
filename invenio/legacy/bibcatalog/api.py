# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2009, 2010, 2011, 2013 CERN.
##
## Invenio is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## Invenio is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Invenio; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Provide a "ticket" interface with a request tracker.
See: https://twiki.cern.ch/twiki/bin/view/Inspire/SystemDesignBibCatalogue
This creates an instance of the class that has been configured for this installation,
or returns None if no ticket system is configured.
"""
from invenio.config import CFG_BIBCATALOG_SYSTEM

bibcatalog_system = None
if CFG_BIBCATALOG_SYSTEM == 'RT':
    from invenio.bibcatalog_system_rt import BibCatalogSystemRT
    bibcatalog_system = BibCatalogSystemRT()
elif CFG_BIBCATALOG_SYSTEM == 'EMAIL':
    from invenio.bibcatalog_system_email import BibCatalogSystemEmail
    bibcatalog_system = BibCatalogSystemEmail()
