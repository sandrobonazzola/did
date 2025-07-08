"""
Redmine stats

Config example::

    [redmine]
    type = redmine
    url = https://redmine.example.com/
    login = <user_db_id>
    activity_days = 30

Use ``login`` to set the database user id in Redmine (number not login
name).  See the :doc:`config` docs for details on using aliases.  Use
``activity_days`` to override the default 30 days of activity paging,
this has to match to the server side setting, otherwise the plugin will
miss entries.

"""

import datetime
from argparse import Namespace
from typing import Optional, cast

import dateutil
import dateutil.parser
import feedparser  # type: ignore[import-untyped]

from did.base import Config, ReportError, User
from did.stats import Stats, StatsGroup
from did.utils import log

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Activity
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class Activity():
    """ Redmine Activity """
    # pylint: disable=too-few-public-methods

    def __init__(self, data: feedparser.FeedParserDict) -> None:
        self.data: feedparser.FeedParserDict = data
        self.title: str = str(data.title)

    def __str__(self) -> str:
        """ String representation """
        return str(self.title)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class RedmineStats(Stats):
    """ Redmine Stats """

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional["RedmineStatsGroup"] = None,
                 user: Optional[User] = None) -> None:
        self.parent: "RedmineStatsGroup"
        self.user: User
        self.options: Namespace
        super().__init__(option=option, name=name, parent=parent, user=user)

    def fetch(self) -> None:
        raise NotImplementedError("Not implemented")


class RedmineActivity(RedmineStats):
    """ Redmine Activity Stats """

    def fetch(self) -> None:
        log.info("Searching for activity by %s", self.user)
        results = []

        from_date = self.options.until.date
        while from_date > self.options.since.date:
            feed_url = (
                f"{self.parent.url}/activity.atom?"
                f"user_id={self.user.login}"
                f"&from={from_date.strftime('%Y-%m-%d')}"
                )
            log.debug("Feed url: %s", feed_url)
            feed: feedparser.FeedParserDict = feedparser.parse(feed_url)
            for entry in cast(list[feedparser.FeedParserDict], feed.entries):
                updated: datetime.date = dateutil.parser.parse(
                    str(entry.updated)).date()
                if updated >= self.options.since.date:
                    results.append(entry)
            from_date = from_date - self.parent.activity_days

        self.stats = [Activity(activity) for activity in results]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class RedmineStatsGroup(StatsGroup):
    """ Redmine Stats """

    # Default order
    order = 550

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional[StatsGroup] = None,
                 user: Optional[User] = None) -> None:
        name = f"Redmine activity on {option}"
        super().__init__(option=option, name=name, parent=parent, user=user)
        config = dict(Config().section(option))
        # Check server url
        try:
            self.url = config["url"]
        except KeyError as exc:
            raise ReportError(f"No Redmine url set in the [{option}] section") from exc
        try:
            self.activity_days = datetime.timedelta(float(config["activity_days"]))
        except KeyError:
            # 30 is value of activity_days_default
            self.activity_days = datetime.timedelta(30)
        # Create the list of stats
        self.stats = [
            RedmineActivity(
                option=f"{option}-activity", parent=self,
                name=f"Redmine activity on {option}"),
            ]
