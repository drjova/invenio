# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015 CERN.
#
# Invenio is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""Flask-IIIF extension."""

from flask_iiif import IIIF
from flask_iiif.errors import MultimediaError

from invenio.modules.documents.utils import uuid_to_path

iiif = IIIF()

__all__ = ('setup_app', )


def setup_app(app):
    """Setup iiif extension."""
    try:
        assert 'invenio.modules.documents' not in \
            app.config['PACKAGES_EXCLUDE']
    except AssertionError:
        raise MultimediaError(
            "Could not initialize the Flask-IIIF extension because "
            "`~invenio.modules.docuements` is missing"
        )
    else:
        iiif.init_app(app)
        iiif.init_restful(app.extensions['restful'])
        iiif.uuid_to_path_handler(uuid_to_path)
        app.config['IIIF_CACHE_HANDLER'] = 'invenio.ext.cache:cache'
    return app
