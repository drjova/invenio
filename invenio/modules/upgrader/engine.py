# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2012, 2013 CERN.
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
Invenio upgrade engine.

Usage (via inveniomanage)::

  inveniomanage upgrade create recipe -r invenio -p ~/src/invenio/modules/miscutil/lib/upgrades/
  inveniomanage upgrade create release -r invenio -p ~/src/invenio/modules/miscutil/lib/upgrades/
  inveniomanage upgrade show applied
  inveniomanage upgrade show pending
  inveniomanage upgrade check
  inveniomanage upgrade run

Recommendations for writing upgrades
------------------------------------

 * An upgrade must be self-contained. DO NOT IMPORT ANYTHING from Invenio
   unless absolutely necessary. Reasons: 1) If a it depends on other Invenio
   modules, then their API must be very stable and backwards-compatible.
   Otherwise when an upgrade is applied two years later, the Invenio function
   might have evolved and the upgrade will fail. 2) Furthermore upgrades are
   *LOADED BEFORE* actually being installed into site-packages  (e.g. when
   "make check-upgrade" are being run). This means that an upgrade cannot
   assume anything about which version of Invenio is installed, and thus if
   the imported module is available or not.
 * Once an upgrade have been committed to master/maint, no fiddling is allowed
   afterwards. If you want to correct a mistake, make an new upgrade instead.
 * All upgrades must depend on a previous upgrade (except for your first
   upgrade).
 * For every software release, make a '<repository>_release_<x>_<y>_<z>.py'
   that depends on all upgrades between the previous release and the new, so
   future upgrades can depend on this upgrade. The command
   --upgrade-create-release-recipe can help you with this.
 * Upgrades may query for user input, but must be able to run in unattended
   mode when --yes-i-know option is being used, thus good defaults/guessing
   should be used.

Upgrade dependency graph
------------------------
The upgrades form a *dependency graph* that must be without cycles (i.e.
a DAG). The upgrade engine supports having several independent graphs (you
normally want one graph for Invenio and one for your overlay). The graphs are
defined using via a filename prefix using the pattern
(<repository>_<date>_<name>.py).

The upgrade engine will run upgrades in topological order (i.e upgrades
will be run respecting the dependency graph). The engine will detect cycles in
the graph and will refuse to run any upgrades until the cycles have been
broken.

Upgrade modules
---------------
Upgrades are implemented as normal Python modules. They must implement the
methods do_upgrade() and info() and contain a list variable 'depends_on'.
Optionally they may implement the methods estimate(), pre_upgrade(),
post_upgrade().

The upgrade engine expects that Invenio upgrades are located in
in $(top_srcdir)/modules/miscutil/lib/upgrades/ and
CFG_PREFIX/lib/python/invenio/upgrades/ respectively.

An upgrade can only depend on upgrades in the same repository (i.e. the same
graph).

A note on upgrade pre-checks prior to installation
----------------------------------------------------
An important feature of the upgrade engine is the ability to run upgrade
pre-checks prior to actually being installed into site-packages. This allows
a system administrator to validate the upgrades prior to running make install,
where it would be too late to discover issues and roll-back.

This means that upgrades cannot assume anything about loaded Invenio modules.
E.g. the following import::

  from invenio.utils.autodiscovery import create_enhanced_plugin_builder

will fail on 1.0.0 while it works on 1.1.0. If the above import statement is
put at the module-level (which you would normally do), the upgrade will never
be loaded when the user is on 1.0.0 and the entire upgrade process will most
likely fail. If on the other hand, the import is put in the pre-check function,
the upgrade will be loaded, but the pre-check will fail and the user will be
properly notified.
"""

from __future__ import absolute_import

from datetime import date, datetime
import logging
import os
import os.path
import re
import subprocess
import sys
import warnings

from sqlalchemy import desc
from werkzeug.utils import import_string
from flask import current_app
from invenio.ext.sqlalchemy import db

from .models import Upgrade


UPGRADE_TEMPLATE = """# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) %(year)s CERN.
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

import warnings
from sqlalchemy import *
from invenio.ext.sqlalchemy import db
from invenio.utils.text import wait_for_user


depends_on = %(depends_on)s


def info():
    return "Short description of upgrade displayed to end-user"


def do_upgrade():
    \"\"\" Implement your upgrades here  \"\"\"
    pass


def estimate():
    \"\"\"  Estimate running time of upgrade in seconds (optional). \"\"\"
    return 1


def pre_upgrade():
    \"\"\"  Run pre-upgrade checks (optional). \"\"\"
    # Example of raising errors:
    # raise RuntimeError("Description of error 1", "Description of error 2")


def post_upgrade():
    \"\"\"  Run post-upgrade checks (optional). \"\"\"
    # Example of issuing warnings:
    # warnings.warn("A continuable error occurred")
"""


def dummy_signgature():
    """ Dummy function signature for pluginutils """
    pass


def _upgrade_doc_mapper(x):
    """ Map function for ingesting documentation strings into plug-ins """
    try:
        x["__doc__"] = x['info']().split("\n")[0].strip()
    except Exception:
        x["__doc__"] = ''
    return x


class InvenioUpgraderLogFormatter(logging.Formatter):
    """
    Custom logging formatter allowing different log formats for different
    error levels.
    """
    def __init__(self, fmt, **overwrites):
        self.fmt = fmt
        self.overwrites = overwrites
        self.prefix = ''
        self.plugin_id = ''
        logging.Formatter.__init__(self, fmt)

    def get_level_fmt(self, level):
        """ Get format for log level """
        key = None
        if level == logging.DEBUG:
            key = 'debug'
        elif level == logging.INFO:
            key = 'info'
        elif level == logging.WARNING:
            key = 'warning'
        elif level == logging.ERROR:
            key = 'error'
        elif level == logging.CRITICAL:
            key = 'critical'
        return self.overwrites.get(key, self.fmt)

    def format(self, record):
        """ Format log record """
        format_orig = self._fmt
        self._fmt = self.get_level_fmt(record.levelno)
        record.prefix = self.prefix
        record.plugin_id = self.plugin_id
        result = logging.Formatter.format(self, record)
        self._fmt = format_orig
        return result

#
# Upgrade engine
#


class InvenioUpgrader(object):
    """
    Class responsible for loading, sorting and executing upgrades

    A note on cross graph dependencies: An upgrade is uniquely identified
    by it's id (part of the filename). This means we do not get into
    a situation where an upgrade id will exist in two repositories. One
    repository will simply overwrite the other on install.
    """
    FILE_LOG_FMT = '*%(prefix)s %(asctime)s %(levelname)-8s ' \
                   '%(plugin_id)s%(message)s'
    CONSOLE_LOG_INFO_FMT = '>>> %(prefix)s%(message)s'
    CONSOLE_LOG_FMT = '>>> %(prefix)s%(levelname)s: %(message)s'

    def __init__(self, packages=None, global_pre_upgrade=None,
                 global_post_upgrade=None):
        """
        @param global_pre_upgrade: List of callables. Each check will be
            executed once per upgrade-batch run. Useful e.g. to check if
            bibsched is running.
        @param global_post_upgrade: List of callables. Each check will be
            executed once per upgrade-batch run. Useful e.g. to tell users
            to start bibsched again.
        """
        self.upgrades = None
        self.history = {}
        self.ordered_history = []

        self.global_pre_upgrade = global_pre_upgrade or [
            pre_check_bibsched
        ]
        self.global_post_upgrade = global_post_upgrade or [
            post_check_bibsched
        ]

        self.packages = packages or \
            current_app.extensions['registry']['packages']

        # Warning related
        self.old_showwarning = None
        self.warning_occured = 0
        self._logger = None
        self._logger_file_fmtter = InvenioUpgraderLogFormatter(
            self.FILE_LOG_FMT)
        self._logger_console_fmtter = InvenioUpgraderLogFormatter(
            self.CONSOLE_LOG_FMT, info=self.CONSOLE_LOG_INFO_FMT,)

    def estimate(self, upgrades):
        """
        Estimate the time needed to apply upgrades.

        If an upgrades does not specify and estimate it is assumed to be
        in the order of 1 second.

        @param upgrades: List of upgrades sorted in topological order.
        """
        val = 0
        for u in upgrades:
            if 'estimate' in u:
                val += u['estimate']()
            else:
                val += 1
        return val

    def human_estimate(self, upgrades):
        """
        Make a human readable string of the estimated time to complete the
        upgrades

        @param upgrades: List of upgrades sorted in topological order.
        """
        val = self.estimate(upgrades)
        if val < 60:
            return "less than 1 minute"
        elif val < 300:
            return "less than 5 minutes"
        elif val < 600:
            return "less than 10 minutes"
        elif val < 1800:
            return "less than 30 minutes"
        elif val < 3600:
            return "less than 1 hour"
        elif val < 3 * 3600:
            return "less than 3 hours"
        elif val < 6 * 3600:
            return "less than 6 hours"
        elif val < 12 * 3600:
            return "less than 12 hours"
        elif val < 86400:
            return "less than 1 day"
        else:
            return "more than 1 day"

    def _setup_log_prefix(self, plugin_id=''):
        """
        Setup custom warning notification
        """
        self._logger_console_fmtter.prefix = '%s: ' % plugin_id
        self._logger_console_fmtter.plugin_id = plugin_id
        self._logger_file_fmtter.prefix = '*'
        self._logger_file_fmtter.plugin_id = '%s: ' % plugin_id

    def _teardown_log_prefix(self):
        """
        Tear down custom warning notification
        """
        self._logger_console_fmtter.prefix = ''
        self._logger_console_fmtter.plugin_id = ''
        self._logger_file_fmtter.prefix = ' '
        self._logger_file_fmtter.plugin_id = ''

    def get_logger(self, logfilename=None):
        """
        Setup logger to allow outputting to both a log file and console at the
        same time.
        """
        if self._logger is None:
            self._logger = logging.getLogger('invenio_upgrader')
            self._logger.setLevel(logging.INFO)

            if logfilename:
                fh = logging.FileHandler(logfilename)
                fh.setLevel(logging.INFO)
                fh.setFormatter(self._logger_file_fmtter)
                self._logger.addHandler(fh)

            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            ch.setFormatter(self._logger_console_fmtter)

            self._logger.addHandler(ch)

            # Replace show warnings (documented in Python manual)
            def showwarning(message, dummy_category, dummy_filename,
                            dummy_lineno, *dummy_args):
                self.warning_occured += 1
                logger = self.get_logger()
                logger.warning(message)
            warnings.showwarning = showwarning

            self._teardown_log_prefix()

        return self._logger

    def has_warnings(self):
        """ Determine if a warning has occurred in this upgrader instance. """
        return self.warning_occured != 0

    def get_warnings_count(self):
        """ Get number of warnings issued """
        return self.warning_occured

    def pre_upgrade_checks(self, upgrades):
        """
        Run upgrade pre-checks prior to applying upgrades. Pre-checks should
        in general be fast to execute. Pre-checks may the use the wait_for_user
        function, to query the user for confirmation, but should respect the
        --yes-i-know option to run unattended.

        All pre-checks will be executed even if one fails, however if one pre-
        check fails, the upgrade process will be stopped and the user warned.

        @param upgrades: List of upgrades sorted in topological order.
        """
        errors = []

        for check in self.global_pre_upgrade:
            self._setup_log_prefix(plugin_id=check.__name__)
            try:
                check()
            except RuntimeError, e:
                errors.append((check.__name__, e.args))

        for u in upgrades:
            if 'pre_upgrade' in u:
                self._setup_log_prefix(plugin_id=u['id'])
                try:
                    u['pre_upgrade']()
                except RuntimeError, e:
                    errors.append((u['id'], e.args))

        self._teardown_log_prefix()

        self._check_errors(errors, "Pre-upgrade check for %s failed with the"
                           " following errors:")

    def _check_errors(self, errors, prefix):
        """
        Check for errors and possible raise and format an error message.

        @param errors: List of error messages.
        @param prefix: str, Prefix message for error messages
        """
        args = []

        for uid, messages in errors:
            error_msg = []
            error_msg.append(prefix % uid)
            for msg in messages:
                error_msg.append(" (-) %s" % msg)
            args.append("\n".join(error_msg))

        if args:
            raise RuntimeError(*args)

    def post_upgrade_checks(self, upgrades):
        """
        Run post-upgrade checks after applying all pending upgrades. Post
        checks may be used to emit warnings encountered when applying an
        upgrade, but post-checks can also be used to advice the user to run
        re-indexing or similar long running processes.

        Post-checks may query for user-input, but should respect the
        --yes-i-know option to run in an unattended mode.

        All applied upgrades post-checks are executed.

        @param upgrades: List of upgrades sorted in topological order.
        """
        errors = []

        for u in upgrades:
            if 'post_upgrade' in u:
                self._setup_log_prefix(plugin_id=u['id'])
                try:
                    u['post_upgrade']()
                except RuntimeError, e:
                    errors.append((u['id'], e.args))

        for check in self.global_post_upgrade:
            self._setup_log_prefix(plugin_id=check.__name__)
            try:
                check()
            except RuntimeError, e:
                errors.append((check.__name__, e.args))

        self._teardown_log_prefix()

        self._check_errors(errors, "Post-upgrade check for %s failed with the "
                           "following errors:")

    def apply_upgrade(self, upgrade):
        """
        Apply a upgrade and register that it was successful.

        A upgrade may throw a RuntimeError, if an unrecoverable error happens.

        @param upgrade: A single upgrade
        """
        self._setup_log_prefix(plugin_id=upgrade['id'])

        try:  # Nested due to Python 2.4
            try:
                upgrade['do_upgrade']()
                self.register_success(upgrade)
            except RuntimeError, e:
                msg = ["Upgrade error(s):"]

                for m in e.args:
                    msg.append(" (-) %s" % m)

                logger = self.get_logger()
                logger.error("\n".join(msg))

                raise RuntimeError(
                    "Upgrade '%s' failed. Your installation is in an"
                    " inconsistent state. Please manually review the upgrade "
                    "and resolve inconsistencies." % upgrade['id']
                )
        finally:
            self._teardown_log_prefix()

    def load_history(self):
        """
        Load upgrade history from database table.

        If upgrade table does not exists, the history is assumed to be empty.
        """
        if not self.history:
            query = Upgrade.query.order_by(desc(Upgrade.applied))

            for u in query.all():
                self.history[u.upgrade] = u.applied
                self.ordered_history.append(u.upgrade)

    def latest_applied_upgrade(self, repository='invenio'):
        """
        Get the latest applied upgrade for a repository.
        """
        u = Upgrade.query.filter(
            Upgrade.upgrade.like("%s_%%" % repository)
        ).order_by(desc(Upgrade.applied)).first()

        return u.upgrade if u else None

    def register_success(self, upgrade):
        """ Register a successful upgrade """
        u = Upgrade(upgrade=upgrade['id'], applied=datetime.now())
        db.session.add(u)
        db.session.commit()

    def get_history(self):
        """ Get history of applied upgrades """
        self.load_history()
        return map(lambda x: (x, self.history[x]), self.ordered_history)

    def _load_upgrades(self, remove_applied=True):
        """
        Load upgrade modules

        Upgrade modules are loaded using pluginutils. The pluginutils module
        is either loaded from site-packages via normal or via a user-loaded
        module supplied in the __init__ method. This is useful when the engine
        is running before actually being installed into site-packages.

        @param remove_applied: if True, already applied upgrades will not
            be included, if False the entire upgrade graph will be
            returned.
        """
        from invenio.utils.autodiscovery import create_enhanced_plugin_builder
        from invenio.base.utils import import_submodules_from_packages

        if remove_applied:
            self.load_history()

        plugin_builder = create_enhanced_plugin_builder(
            compulsory_objects={
                'do_upgrade': dummy_signgature,
                'info': dummy_signgature,
            },
            optional_objects={
                'estimate': dummy_signgature,
                'pre_upgrade': dummy_signgature,
                'post_upgrade': dummy_signgature,
            },
            other_data={
                'depends_on': (list, []),
            },
        )

        def builder(plugin):
            plugin_id = plugin.__name__.split('.')[-1]
            data = plugin_builder(plugin)
            data['id'] = plugin_id
            data['repository'] = self._parse_plugin_id(plugin_id)
            return plugin_id, data

        # Load all upgrades from installed packages
        plugins = dict(map(
            builder,
            import_submodules_from_packages(
                'upgrades',
                packages=self.packages
            )
        ))

        return plugins

    def _parse_plugin_id(self, plugin_id):
        """
        Determine repository from plugin id
        """
        m = re.match("(.+)(_\d{4}_\d{2}_\d{2}_)(.+)", plugin_id)
        if m:
            return m.group(1)
        m = re.match("(.+)(_release_)(.+)", plugin_id)
        if m:
            return m.group(1)

        raise RuntimeError("Repository could not be determined from "
                           "the upgrade identifier: %s." % plugin_id)

    def get_upgrades(self, remove_applied=True):
        """
        Get upgrades (ordered according to their dependencies).

        @param remove_applied: Set to false to return all upgrades, otherwise
            already applied upgrades are removed from their graph (incl. all
            their dependencies.
        """
        if self.upgrades is None:
            plugins = self._load_upgrades(remove_applied=remove_applied)

            # List of un-applied upgrades in topological order
            self.upgrades = map(_upgrade_doc_mapper,
                                self.order_upgrades(plugins, self.history))
        return self.upgrades

    def _create_graph(self, upgrades, history={}):
        """
        Create dependency graph from upgrades

        @param upgrades: Dict of upgrades
        @param history: Dict of applied upgrades
        """
        graph_incoming = {}  # nodes their incoming edges
        graph_outgoing = {}  # nodes their outgoing edges

        # Create graph data structure
        for mod in upgrades.values():
            # Remove all incoming edges from already applied upgrades
            graph_incoming[mod['id']] = filter(lambda x: x not in history,
                                               mod['depends_on'])
            # Build graph_outgoing
            if mod['id'] not in graph_outgoing:
                graph_outgoing[mod['id']] = []
            for edge in graph_incoming[mod['id']]:
                if edge not in graph_outgoing:
                    graph_outgoing[edge] = []
                graph_outgoing[edge].append(mod['id'])

        return (graph_incoming, graph_outgoing)

    def find_endpoints(self):
        """
        Find upgrade end-points (i.e nodes without dependents).
        """
        plugins = self._load_upgrades(remove_applied=False)

        dummy_graph_incoming, graph_outgoing = self._create_graph(plugins, {})

        endpoints = {}
        for node, outgoing in graph_outgoing.items():
            if not outgoing:
                repository = plugins[node]['repository']
                if repository not in endpoints:
                    endpoints[repository] = []
                endpoints[repository].append(node)

        return endpoints

    def order_upgrades(self, upgrades, history={}):
        """
        Order upgrades according to their dependencies (topological sort using
        Kahn's algorithm - http://en.wikipedia.org/wiki/Topological_sorting).

        @param upgrades: Dict of upgrades
        @param history: Dict of applied upgrades
        """
        graph_incoming, graph_outgoing = self._create_graph(upgrades, history)

        # Removed already applied upgrades (assumes all dependencies prior to
        # this upgrade has been applied).
        for node_id in history.keys():
            start_nodes = [node_id, ]
            while start_nodes:
                node = start_nodes.pop()
                # Remove from direct dependents
                try:
                    for d in graph_outgoing[node]:
                        graph_incoming[d] = filter(lambda x: x != node,
                                                   graph_incoming[d])
                except KeyError:
                    warnings.warn("Ghost upgrade %s detected" % node)

                # Remove all prior dependencies
                if node in graph_incoming:
                    # Get dependencies, remove node, and recursively
                    # remove all dependencies.
                    depends_on = graph_incoming[node]

                    # Add dependencies to check
                    for d in depends_on:
                        graph_outgoing[d] = filter(lambda x: x != node,
                                                   graph_outgoing[d])
                        start_nodes.append(d)

                    del graph_incoming[node]

        # Check for missing dependencies
        for node_id, depends_on in graph_incoming.items():
            for d in depends_on:
                if d not in graph_incoming:
                    raise RuntimeError("Upgrade %s depends on an unknown"
                                       " upgrade %s" % (node_id, d))

        # Nodes with no incoming edges
        start_nodes = filter(lambda x: len(graph_incoming[x]) == 0,
                             graph_incoming.keys())
        topo_order = []

        while start_nodes:
            # Append node_n to list (it has no incoming edges)
            node_n = start_nodes.pop()
            topo_order.append(node_n)

            # For each node m with and edge from n to m
            for node_m in graph_outgoing[node_n]:
                # Remove the edge n to m
                graph_incoming[node_m] = filter(lambda x: x != node_n,
                                                graph_incoming[node_m])
                # If m has no incoming edges, add it to start_nodes.
                if not graph_incoming[node_m]:
                    start_nodes.append(node_m)

        for node, edges in graph_incoming.items():
            if edges:
                raise RuntimeError("The upgrades have at least one cyclic "
                                   "dependency involving %s." % node)

        return map(lambda x: upgrades[x], topo_order)


#
# Global pre/post-checks
#
def pre_check_bibsched():
    """
    Check if bibsched is running
    """
    logger = logging.getLogger('invenio_upgrader')
    logger.info("Checking bibsched process...")

    output, error = subprocess.Popen(["bibsched", "status"],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE).communicate()

    is_manual = False
    is_0_running = False
    for line in (output + error).splitlines():
        if 'BibSched queue running mode: MANUAL' in line:
            is_manual = True
        if 'Running processes: 0' in line:
            is_0_running = True

    stopped = is_manual and is_0_running

    if not stopped:
        raise RuntimeError("Bibsched is running. Please stop bibsched "
                           "using the command:\n$ bibsched stop")


def post_check_bibsched():
    """
    Inform user to start bibsched again
    """
    logger = logging.getLogger('invenio_upgrader')
    logger.info("Remember to start bibsched again:\n$ bibsched start")
    return True


#
# Commands
#

def cmd_upgrade_check(upgrader=None):
    """ Command for running pre-upgrade checks """
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger()

    try:
        # Run upgrade pre-checks
        upgrades = upgrader.get_upgrades()

        # Check if there's anything to upgrade
        if not upgrades:
            logger.info("All upgrades have been applied.")
            sys.exit(0)

        logger.info("Following upgrade(s) have not been applied yet:")
        for u in upgrades:
            title = u['__doc__']
            if title:
                logger.info(" * %s (%s)" % (u['id'], title))
            else:
                logger.info(" * %s" % u['id'])

        logger.info("Running pre-upgrade checks...")
        upgrader.pre_upgrade_checks(upgrades)
        logger.info("Upgrade check successful - estimated time for upgrading"
                    " Invenio is %s..." % upgrader.human_estimate(upgrades))
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        logger.error("Upgrade check failed. Aborting.")
        sys.exit(1)


def cmd_upgrade(upgrader=None):
    """ Command for applying upgrades """
    from invenio.config import CFG_LOGDIR
    from invenio.utils.text import wrap_text_in_a_box, wait_for_user

    logfilename = os.path.join(CFG_LOGDIR, 'invenio_upgrader.log')
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger(logfilename=logfilename)

    try:
        upgrades = upgrader.get_upgrades()

        if not upgrades:
            logger.info("All upgrades have been applied.")
            return

        logger.info("Following upgrade(s) will be applied:")

        for u in upgrades:
            title = u['__doc__']
            if title:
                logger.info(" * %s (%s)" % (u['id'], title))
            else:
                logger.info(" * %s" % u['id'])

        logger.info("Running pre-upgrade checks...")
        upgrader.pre_upgrade_checks(upgrades)

        logger.info("Calculating estimated upgrade time...")
        estimate = upgrader.human_estimate(upgrades)

        wait_for_user(wrap_text_in_a_box(
            "WARNING: You are going to upgrade your installation "
            "(estimated time: %s)!" % estimate))

        for u in upgrades:
            title = u['__doc__']
            if title:
                logger.info("Applying %s (%s)" % (u['id'], title))
            else:
                logger.info("Applying %s" % u['id'])
            upgrader.apply_upgrade(u)

        logger.info("Running post-upgrade checks...")
        upgrader.post_upgrade_checks(upgrades)

        if upgrader.has_warnings():
            logger.warning("Upgrade completed with %s warnings - please check "
                           "log-file for further information:\nless %s"
                           % (upgrader.get_warnings_count(), logfilename))
        else:
            logger.info("Upgrade completed successfully.")
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        logger.info("Please check log file for further information:\n"
                    "less %s" % logfilename)
        sys.exit(1)


def cmd_upgrade_show_pending(upgrader=None):
    """ Command for showing upgrades ready to be applied """
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger()

    try:
        upgrades = upgrader.get_upgrades()

        if not upgrades:
            logger.info("All upgrades have been applied.")
            return

        logger.info("Following upgrade(s) are ready to be applied:")

        for u in upgrades:
            title = u['__doc__']
            if title:
                logger.info(" * %s (%s)" % (u['id'], title))
            else:
                logger.info(" * %s" % u['id'])
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        sys.exit(1)


def cmd_upgrade_show_applied(upgrader=None):
    """ Command for showing all upgrades already applied. """
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger()

    try:
        upgrades = upgrader.get_history()

        if not upgrades:
            logger.info("No upgrades have been applied.")
            return

        logger.info("Following upgrade(s) have been applied:")

        for u_id, applied in upgrades:
            logger.info(" * %s (%s)" % (u_id, applied))
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        sys.exit(1)


def cmd_upgrade_create_release_recipe(pkg_path, repository=None,
                                      output_path=None, upgrader=None):
    """
    Create a new release upgrade recipe (for developers).
    """
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger()

    try:
        endpoints = upgrader.find_endpoints()

        if not endpoints:
            logger.error("No upgrades found.")
            sys.exit(1)

        depends_on = []
        for repo, upgrades in endpoints.items():
            depends_on.extend(upgrades)

        return cmd_upgrade_create_standard_recipe(pkg_path,
                                                  repository=repository,
                                                  depends_on=depends_on,
                                                  release=True,
                                                  output_path=output_path,
                                                  upgrader=upgrader)
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        sys.exit(1)


def cmd_upgrade_create_standard_recipe(pkg_path, repository=None,
                                       depends_on=None, release=False,
                                       upgrader=None, output_path=None):
    """
    Create a new upgrade recipe (for developers).
    """
    if not upgrader:
        upgrader = InvenioUpgrader()
    logger = upgrader.get_logger()

    try:
        path, found_repository = _upgrade_recipe_find_path(pkg_path)

        if output_path:
            path = output_path

        if not repository:
            repository = found_repository

        if not os.path.exists(path):
            raise RuntimeError("Path does not exists: %s" % path)
        if not os.path.isdir(path):
            raise RuntimeError("Path is not a directory: %s" % path)

        # Generate upgrade filename
        if release:
            filename = "%s_release_x_y_z.py" % repository
        else:
            filename = "%s_%s_%s.py" % (repository,
                                        date.today().strftime("%Y_%m_%d"),
                                        'rename_me')

        # Check if generated repository name can be parsed
        test_repository = upgrader._parse_plugin_id(filename[:-3])
        if repository != test_repository:
            raise RuntimeError(
                "Generated repository name cannot be parsed. "
                "Please override it with --repository option."
            )

        upgrade_file = os.path.join(path, filename)

        if os.path.exists(upgrade_file):
            raise RuntimeError(
                "Could not generate upgrade - %s already exists."
                % upgrade_file
            )

        # Determine latest installed upgrade
        if depends_on is None:
            depends_on = ["CHANGE_ME"]

            u = upgrader.latest_applied_upgrade(repository=repository)
            if u:
                depends_on = [u]

        # Write upgrade template file
        f = open(upgrade_file, 'w')
        f.write(UPGRADE_TEMPLATE % {'depends_on': depends_on,
                                    'repository': repository,
                                    'year': date.today().year})
        f.close()

        logger.info("Created new upgrade %s" % upgrade_file)
    except RuntimeError, e:
        for msg in e.args:
            logger.error(unicode(msg))
        sys.exit(1)


#
# Invenio helper functions
#
def _upgrade_recipe_find_path(import_str, create=True):
    """
    Determine repository name and path for new upgrade, based on package
    import path.
    """
    try:
        # Import package
        m = import_string(import_str)

        # Check if package or module
        if m.__package__ is not None:
            raise RuntimeError(
                "Expected package but found module at '%s'." % import_str
            )

        # Create upgrade directory if it does not exists
        path = os.path.join(os.path.dirname(m.__file__), "upgrades")
        if not os.path.exists(path) and create:
            os.makedirs(path)

        # Create init file if it does not exists
        init = os.path.join(path, "__init__.py")
        if not os.path.exists(init) and create:
            open(init, 'a').close()

        repository = m.__name__.split(".")[-1]

        return (path, repository)
    except ImportError:
        raise RuntimeError("Could not find module '%s'." % import_str)
    except SyntaxError:
        raise RuntimeError("Module '%s' has syntax errors." % import_str)
