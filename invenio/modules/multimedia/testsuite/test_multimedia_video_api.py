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

"""Multimedia Video API Tests."""

from six import StringIO
from invenio.testsuite import make_test_suite, run_test_suite, InvenioTestCase


class TestMultimediaVideoAPI(InvenioTestCase):

    """Multimedia Video API test case."""

    def setUp(self):
        """Run before the test."""
        # Create an image in memory
        from invenio.modules.multimedia.api import MultimediaVideo
        from invenio.modules.multimedia.errors import MultimediaVideoNotFound

    def tearDown(self):
        """Run after the test."""

    def test_image_resize(self):
        """Test video resize function."""
        self.assertRaises(
            MultimediaVideoNotFound, MultimediaVideo.get_video(999999)
        )

TEST_SUITE = make_test_suite(TestMultimediaVideoAPI)

if __name__ == '__main__':
    run_test_suite(TEST_SUITE)
