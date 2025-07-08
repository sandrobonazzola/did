"""
Trello actions such as created, moved or closed cards

Config example (public)::

    [tools]
    type = trello
    user = member

Config example (private)::

    [tools]
    type = trello
    apikey = ...
    token = ...

Optional arguments::

    board_links = g9mdhdzg
    filters = createCard, updateCard,
        updateCard:idList, updateCard:closed,
        updateCheckItemStateOnCard

    apikey
        https://trello.com/app-key

    token
        http://stackoverflow.com/questions/17178907

    token_file
        the token stored in a file

    boards
        default: all

    filters
        default: all
"""

# Possible API methods to add:
# http://developers.trello.com/advanced-reference/member

import datetime
import json
import urllib.parse
import urllib.request
from argparse import Namespace
from typing import Any, Optional

from did.base import Config, ReportError, User, get_token
from did.stats import Stats, StatsGroup
from did.utils import log, pretty, split

DEFAULT_FILTERS = [
    "commentCard", "createCard", "updateCard",
    "updateCard:idList", "updateCard:closed",
    "updateCheckItemStateOnCard"]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloStats(Stats):
    """ Trello stats """

    def __init__(self, *,
                 trello: Optional["TrelloAPI"],
                 filt: str,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional["TrelloStatsGroup"] = None,
                 options: Optional[Namespace] = None) -> None:
        self.options: Namespace
        self.parent: TrelloStatsGroup
        super().__init__(option=option, name=name, parent=parent,
                         options=options)
        self.filt = filt
        self.trello: Optional[TrelloAPI] = trello

    def fetch(self) -> None:
        """ Fetch the stats (to be implemented by respective class). """
        raise NotImplementedError()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello API
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloAPI():
    """ Trello API """

    def __init__(self, stats: "TrelloStatsGroup", config: dict[str, str]) -> None:
        self.stats: TrelloStatsGroup = stats

        self.key: str = config['apikey']
        self.token: str = config['token']
        self.username: str = config['user'] if "user" in config else "me"
        self.board_links: list[str] = split(config['board_links'])
        self.board_ids: list[str] = self.board_links_to_ids()

    def get_actions(self,
                    filter_param: str,
                    since: Optional[datetime.date] = None,
                    before: Optional[datetime.date] = None,
                    limit: int = 1000) -> list[dict[str, Any]]:
        """
        Example of data structure:
        https://api.trello.com/1/members/ben/actions?limit=2
        """
        if limit > 1000:
            raise NotImplementedError(
                "Fetching more than 1000 items is not implemented")
        actions = urllib.parse.urlencode({
            "key": self.key,
            "token": self.token,
            "filter": filter_param,
            "limit": limit,
            "since": str(since),
            "before": str(before)})
        resp = self.stats.session.open(
            f"{self.stats.url}/members/{self.username}/actions?{actions}")

        json_actions = json.loads(resp.read())
        log.data(pretty(json_actions))
        # print[act for act in actions if "shortLink" not in
        # act['data']['board'].keys()]
        dict_actions = [act
                        for act in json_actions
                        if act['data']['board']['id'] in self.board_ids]
        return dict_actions

    def board_links_to_ids(self) -> list[str]:
        """ Convert board links to ids """
        encoded_query = urllib.parse.urlencode(
            {
                "key": self.key,
                "token": self.token,
                "fields": "shortLink"
                }
            )
        resp = self.stats.session.open(
            f"{self.stats.url}/members/{self.username}/boards?{encoded_query}")
        boards = json.loads(resp.read())

        return [board['id'] for board in boards if self.board_links == [""]
                or board['shortLink'] in self.board_links]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello createCard
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloCardsCreated(TrelloStats):
    """ Trello cards created """

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for cards created in %s by %s",
            self.parent.option, self.user)
        actions = [
            act['data']['card']['name']
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)]
        self.stats = sorted(list(set(actions)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello updateCard
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloCardsUpdated(TrelloStats):
    """ Trello cards updated"""

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for cards updated in %s by %s",
            self.parent.option, self.user)
        actions = [
            act['data']['card']['name']
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)]
        self.stats = sorted(list(set(actions)))


class TrelloCardsCommented(TrelloStats):
    """ Trello cards commented"""

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for cards commented in %s by %s",
            self.parent.option, self.user)
        actions = [
            act['data']['card']['name']
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)]
        self.stats = sorted(list(set(actions)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello updateCard:closed
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloCardsClosed(TrelloStats):
    """ Trello cards closed"""

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for cards closed in %s by %s",
            self.parent.option, self.user)
        status = {True: 'closed',
                  False: 'opened'}
        actions = [
            f"{act['data']['card']['name']}: {status[act['data']['card']['closed']]}"
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)
            ]

        self.stats = sorted(list(set(actions)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello updateCard:idList
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloCardsMoved(TrelloStats):
    """ Trello cards moved"""

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for cards moved in %s by %s",
            self.parent.option, self.user)
        actions = [
            (f"[{act['data']['card']['name']}]"
             f" moved from [{act['data']['listBefore']['name']}]"
             f" to [{act['data']['listAfter']['name']}]")
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)]

        self.stats = sorted(list(set(actions)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello updateCheckItemStateOnCard
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloCheckItem(TrelloStats):
    """ Trello checklist items completed"""

    def fetch(self) -> None:
        if self.trello is None:
            raise RuntimeError("Trello API not initialized")
        log.info(
            "Searching for CheckItem completed in %s by %s",
            self.parent.option, self.user)
        actions = [
            f"{act['data']['card']['name']}: {act['data']['checkItem']['name']}"
            for act in self.trello.get_actions(
                filter_param=self.filt,
                since=self.options.since.date,
                before=self.options.until.date)]
        self.stats = sorted(list(set(actions)))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Trello Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class TrelloStatsGroup(StatsGroup):
    """ Trello stats group """

    # Default order
    order = 450

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional[StatsGroup] = None,
                 user: Optional[User] = None) -> None:
        name = f"Trello updates for {option}"
        super().__init__(option=option, name=name, parent=parent, user=user)

        # map appropriate API methods to Classes
        filter_map: dict[str, dict[str, type[TrelloStats]]] = {
            'Boards': {},
            'Lists': {},
            'Cards': {
                'commentCard': TrelloCardsCommented,
                'updateCard': TrelloCardsUpdated,
                'updateCard:closed': TrelloCardsClosed,
                'updateCard:idList': TrelloCardsMoved,
                'createCard': TrelloCardsCreated},
            'Checklists': {
                'updateCheckItemStateOnCard': TrelloCheckItem}
            }
        self._session: Optional[urllib.request.OpenerDirector] = None
        self.url: str = "https://trello.com/1"
        config = dict(Config().section(option))
        token = get_token(config)
        if token is not None:
            config["token"] = token
        positional_args = ['apikey', 'token']
        if (not set(positional_args).issubset(set(config.keys()))
                and "user" not in config):
            raise ReportError(
                f"""No ('{"' and '".join(positional_args)}') """
                f"or 'user' set in the [{option}] section")
        optional_args = ["board_links", "apikey"]
        for arg in optional_args:
            if arg not in config:
                config[arg] = ""

        # Skip API instance initialization when building options
        if self.options is None:
            trello = None
        else:
            trello = TrelloAPI(stats=self, config=config)

        try:
            filters = split(config["filters"])
        except KeyError:
            filters = DEFAULT_FILTERS
        for filt_group in sorted(filter_map):
            for filt in sorted(filter_map[filt_group]):
                if filters != [""] and filt not in filters:
                    continue
                self.stats.append(filter_map[filt_group][filt](
                    trello=trello,
                    filt=filt,
                    option=f"{option}-{filt}",
                    parent=self))

    @property
    def session(self) -> urllib.request.OpenerDirector:
        """ Initialize the session """
        if self._session is None:
            self._session = urllib.request.build_opener(
                urllib.request.HTTPHandler)
        return self._session
