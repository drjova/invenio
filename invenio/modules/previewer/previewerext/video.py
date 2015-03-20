# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2015 CERN.
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

"""Implemenent Video previewer plugin."""

from flask import render_template, request, current_app
from invenio.modules.multimedia.api import MultimediaVideo


def can_preview(f):
    """Return True for PDFs, False for others."""
    return f.superformat.lower() in ['.mp4', '.ogv', '.webm']


def preview(f):
    """Return appropiate template and pass the file and an embed flag."""
    record_id = f.get_recid()
    videos = MultimediaVideo.get_video(record_id)
    return render_template(
        "previewer/video.html", videos=videos.videos, posters=videos.posters
    )
