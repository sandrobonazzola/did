"""
MoinMoin wiki stats about updated pages

Config example::

    [wiki]
    type = wiki
    wiki test = http://moinmo.in/

The optional key 'api' can be used to change the default
xmlrpc api endpoint::

    [wiki]
    type = wiki
    api = ?action=xmlrpc2
    wiki test = http://moinmo.in/
"""

import xmlrpc.client
from argparse import Namespace
from typing import Any, Optional, cast

from did.base import Config, ConfigError, ReportError, User
from did.stats import Stats, StatsGroup
from did.utils import item

DEFAULT_API = '?action=xmlrpc2'


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Wiki Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class WikiStats(Stats):
    """ Wiki stats """

    def __init__(self, *,
                 option: str,
                 name: str,
                 parent: Optional["WikiStatsGroup"],
                 url: str,
                 api: str = DEFAULT_API) -> None:
        self.options: Namespace
        self.user: User
        self.url: str = url
        self.api: str = api or DEFAULT_API
        self.parent: "WikiStatsGroup"
        self.changes: int = 0
        self.proxy: xmlrpc.client.ServerProxy = xmlrpc.client.ServerProxy(
            f"{url}{self.api}")
        Stats.__init__(self, option, name, parent)

    def fetch(self) -> None:
        raise NotImplementedError("Subclasses must implement this method")


class WikiChanges(WikiStats):
    """ Wiki changes """

    def __init__(self, *,
                 option: str,
                 name: str,
                 parent: Optional["WikiStatsGroup"] = None,
                 url: str,
                 api: str = DEFAULT_API) -> None:
        super().__init__(option=option, name=name,
                         parent=parent, url=url, api=api)

    def fetch(self) -> None:
        try:
            changes: list[dict[str, Any]] = cast(
                list[dict[str, Any]],
                self.proxy.getRecentChanges(self.options.since.datetime))
        except (xmlrpc.client.Error, OSError) as error:
            raise ReportError(
                f"Unable to fetch wiki changes from '{self.url}' "
                f"because of '{error}'.") from error
        for change in changes:
            if (change["author"] == self.user.login
                    and change["lastModified"] < self.options.until.date):
                self.changes += 1
                url = self.url + change["name"]
                if url not in self.stats:
                    self.stats.append(url)
        self.stats.sort()

    def header(self) -> None:
        """ Show summary header. """
        # Different header for wiki:
        # Updates on xxx: x changes of y pages
        item(
            f'{self.name}: {self.changes} '
            f'change{"" if self.changes == 1 else "s"} '
            f'of {len(self.stats)} page{"" if len(self.stats) == 1 else "s"}',
            level=0,
            options=self.options)

    def merge(self, other: Stats) -> None:
        """ Merge another stats. """
        Stats.merge(self, other)
        if not isinstance(other, WikiChanges):
            raise NotImplementedError()
        self.changes += other.changes


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class WikiStatsGroup(StatsGroup):
    """ Wiki stats """

    # Default order
    order = 700

    def __init__(
            self,
            option: str,
            name: Optional[str] = None,
            parent: Optional[StatsGroup] = None,
            user: Optional[User] = None) -> None:
        StatsGroup.__init__(self, option, name, parent, user)
        try:
            api = Config().item(option, 'api')
        except ConfigError:
            api = DEFAULT_API
        for wiki, url in Config().section(option, skip=('type', 'api')):
            self.stats.append(WikiChanges(
                option=wiki, parent=self, url=url, api=api,
                name=f"Updates on {wiki}"))
