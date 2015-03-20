{#
# This file is part of Invenio.
# Copyright (C) 2014 CERN.
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
#}
<div class="row">
    <div class="col-md-12">
        <div class="embed-responsive embed-responsive-16by9">
            <iframe class="embed-responsive-item" src="{{ url_for("previewer.preview", recid=recid) }}"></iframe>
        </div>
    </div>
</div>
<div class="row">
    <div class="col-md-8">
        <h3>{{ bfe_title(bfo, prefix="", suffix="", default="", escape="", highlight="no", separator=" ") }}</h3>
        <p class="lead">{{ bfe_abstract(bfo, ) }}</p>
        <ul class="nav nav-tabs nav-justified" role="tablist">
            <li role="presentation" class="active"><a href="#details" aria-controls="details" role="tab" data-toggle="tab">{{ _("Details") }}</a></li>
            <li role="presentation"><a href="#download" aria-controls="download" role="tab" data-toggle="tab">{{ _("Download") }}</a></li>
            <li role="presentation"><a href="#embed" aria-controls="embed" role="tab" data-toggle="tab">{{ _("Embed") }}</a></li>
        </ul>

        <div class="tab-content">
            <div role="tabpanel" class="tab-pane active" id="details">
                {{ bfe_field(bfo, tag="909C0Y") }}
                {{ _("by") }} {{ bfe_authors(bfo, prefix="", suffix="", default="", escape="", affiliation_suffix=")", extension="[...]", link_author_pages="no", limit="", print_links="yes", separator=" ; ", print_affiliations="no", highlight="no", interactive="no", affiliation_prefix=" (") }}
                {{ bfe_copyright(bfo, ) }}
            </div>
            <div role="tabpanel" class="tab-pane" id="download">...</div>
            <div role="tabpanel" class="tab-pane" id="ebmed">...</div>
        </div>

    </div>
    <div class="col-md-4">
    </div>
</div>
{# WebTags #}
{{ tfn_webtag_record_tags(record['recid'], current_user.get_id())|prefix('<hr />') }}

{{ tfn_get_back_to_search_links(record['recid'])|wrap(prefix='<div class="pull-right linksbox">', suffix='</div>') }}
