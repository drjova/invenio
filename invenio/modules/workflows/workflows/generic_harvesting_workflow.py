## This file is part of Invenio.
## Copyright (C) 2012 CERN.
##
## Invenio is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## Invenio is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Invenio; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111 1307, USA.

"""Implements an example of a typical ingestion workflow for MARCXML records"""

from ..tasks.marcxml_tasks import (get_repositories_list,
                                   init_harvesting,
                                   harvest_records,
                                   get_files_list,
                                   get_eng_uuid_harvested,
                                   get_records_from_file
                                   )

from ..tasks.workflows_tasks import (start_workflow,
                                     wait_for_workflows_to_complete,
                                     workflows_reviews,
                                     get_nb_workflow_created
                                     )

from ..tasks.logic_tasks import (foreach,
                                 endforeach
                                 )

from ..tasks.bibsched_tasks import (write_something_bibsched,
                                    get_and_save_task_parameter
                                    )

from invenio.base.config import CFG_TMPSHAREDDIR


class generic_harvesting_workflow(object):
    workflow = [init_harvesting,
                write_something_bibsched("starting"),
                get_and_save_task_parameter,
                foreach(get_repositories_list(['arxiv']), "repository"),
                [
                    write_something_bibsched("harvesting"),
                    harvest_records,
                    foreach(get_files_list(CFG_TMPSHAREDDIR, get_eng_uuid_harvested)),
                    [
                        foreach(get_records_from_file()),
                        [
                            start_workflow("full_doc_process", None, stop_on_error=True),
                            write_something_bibsched(["Workflow started : ", get_nb_workflow_created, " "]),
                        ],
                        endforeach
                    ],
                    endforeach
                ],
                endforeach,
                write_something_bibsched("waiting workflows"),
                wait_for_workflows_to_complete,
                write_something_bibsched("the end"),
                workflows_reviews
    ]

