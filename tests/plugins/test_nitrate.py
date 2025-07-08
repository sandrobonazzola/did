# coding: utf-8
"""
Tests for the Nitrate plugin
"""

from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

import did.base
from did.plugins.nitrate import (TEST_CASE_COPY_TAG, AutomatedCases,
                                 AutoproposedCases, CopiedCases, ManualCases,
                                 NitratePlans, NitrateRuns, NitrateStats,
                                 NitrateStatsGroup)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Constants
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

INTERVAL = "--since 2021-01-01 --until 2021-01-31"

CONFIG = """
[general]
email = "Test User" <test@example.com>

[nitrate]
type = nitrate
url = https://nitrate.example.com/
"""

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Test Fixtures
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@pytest.fixture(name="mock_user")
def mock_user_fixture() -> did.base.User:
    """Create a mock user for testing"""
    user = did.base.User("Test User <test@example.com>")
    return user


@pytest.fixture(name="mock_options")
def mock_options_fixture() -> Namespace:
    """Create mock options for testing"""
    return Namespace(since="2021-01-01", until="2021-01-31")


@pytest.fixture(name="mock_nitrate_stats_group")
def mock_nitrate_stats_group_fixture(
        mock_user: did.base.User,
        mock_options: Namespace) -> NitrateStatsGroup:
    """Create a mock NitrateStatsGroup for testing"""
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = mock_options
    return group

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Base Class Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def test_nitrate_stats_init(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test NitrateStats initialization"""
    stats = NitrateStats(
        option="test-option",
        name="Test Stats",
        parent=mock_nitrate_stats_group,
        user=mock_user
        )

    assert stats.option == "test-option"
    assert stats.name == "Test Stats"
    assert stats.parent == mock_nitrate_stats_group
    assert stats.user == mock_user


def test_nitrate_stats_fetch_not_implemented(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test that NitrateStats.fetch raises NotImplementedError"""
    stats = NitrateStats(
        option="test-option",
        parent=mock_nitrate_stats_group,
        user=mock_user
        )

    with pytest.raises(NotImplementedError,
                       match="Subclasses must implement fetch"):
        stats.fetch()

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Test Plans Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@patch('did.plugins.nitrate.nitrate')
def test_test_plans_fetch(
        mock_nitrate: Mock,
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup,
        mock_options: Namespace) -> None:
    """Test NitratePlans.fetch method"""
    # Setup mock
    mock_test_plan = Mock()
    mock_test_plan.name = "Test Plan 1"
    mock_nitrate.TestPlan.search.return_value = [mock_test_plan]

    # Create NitratePlans instance
    test_plans = NitratePlans(
        option="test-plans",
        parent=mock_nitrate_stats_group,
        user=mock_user)
    test_plans.options = mock_options

    # Execute fetch
    test_plans.fetch()

    # Verify the search was called with correct parameters
    mock_nitrate.TestPlan.search.assert_called_once_with(
        is_active=True,
        author__email=mock_user.email,
        create_date__gt="2021-01-01",
        create_date__lt="2021-01-31"
        )

    # Verify the stats were populated
    assert len(test_plans.stats) == 1
    assert test_plans.stats[0] == mock_test_plan

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Test Runs Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@patch('did.plugins.nitrate.nitrate')
def test_test_runs_fetch(
        mock_nitrate: Mock,
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup,
        mock_options: Namespace) -> None:
    """Test NitrateRuns.fetch method"""
    # Setup mock
    mock_test_run = Mock()
    mock_test_run.summary = "Test Run 1"
    mock_nitrate.TestRun.search.return_value = [mock_test_run]

    # Create NitrateRuns instance
    test_runs = NitrateRuns(
        option="test-runs",
        parent=mock_nitrate_stats_group,
        user=mock_user)
    test_runs.options = mock_options

    # Execute fetch
    test_runs.fetch()

    # Verify the search was called with correct parameters
    mock_nitrate.TestRun.search.assert_called_once_with(
        default_tester__email=mock_user.email,
        stop_date__gt="2021-01-01",
        stop_date__lt="2021-01-31"
        )

    # Verify the stats were populated
    assert len(test_runs.stats) == 1
    assert test_runs.stats[0] == mock_test_run

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Test Cases Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def test_automated_cases_fetch(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test AutomatedCases.fetch method"""
    # Setup mock cases
    automated_case = Mock()
    automated_case.automated = True

    manual_case = Mock()
    manual_case.automated = False

    copied_case = Mock()
    copied_case.automated = True

    # Setup parent with mock cases and copies
    # pylint: disable=protected-access
    mock_nitrate_stats_group._cases = [
        automated_case, manual_case, copied_case]
    mock_nitrate_stats_group._copies = [copied_case]

    # Create AutomatedCases instance
    automated_cases = AutomatedCases(
        option="automated",
        parent=mock_nitrate_stats_group,
        user=mock_user)

    # Execute fetch
    automated_cases.fetch()

    # Verify only automated non-copied cases are included
    assert len(automated_cases.stats) == 1
    assert automated_cases.stats[0] == automated_case


def test_autoproposed_cases_fetch(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test AutoproposedCases.fetch method"""
    # Setup mock cases
    autoproposed_case = Mock()
    autoproposed_case.autoproposed = True
    autoproposed_case.automated = False

    automated_case = Mock()
    automated_case.autoproposed = True
    automated_case.automated = True

    manual_case = Mock()
    manual_case.autoproposed = False
    manual_case.automated = False

    copied_case = Mock()
    copied_case.autoproposed = True
    copied_case.automated = False

    # Setup parent with mock cases and copies
    # pylint: disable=protected-access
    mock_nitrate_stats_group._cases = [
        autoproposed_case, automated_case, manual_case, copied_case]
    mock_nitrate_stats_group._copies = [copied_case]

    # Create AutoproposedCases instance
    autoproposed_cases = AutoproposedCases(
        option="autoproposed",
        parent=mock_nitrate_stats_group,
        user=mock_user)

    # Execute fetch
    autoproposed_cases.fetch()

    # Verify only autoproposed non-automated non-copied cases
    assert len(autoproposed_cases.stats) == 1
    assert autoproposed_cases.stats[0] == autoproposed_case


def test_manual_cases_fetch(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test ManualCases.fetch method"""
    # Setup mock cases
    manual_case = Mock()
    manual_case.automated = False

    automated_case = Mock()
    automated_case.automated = True

    copied_case = Mock()
    copied_case.automated = False

    # Setup parent with mock cases and copies
    # pylint: disable=protected-access
    mock_nitrate_stats_group._cases = [
        manual_case, automated_case, copied_case]
    mock_nitrate_stats_group._copies = [copied_case]

    # Create ManualCases instance
    manual_cases = ManualCases(
        option="manual",
        parent=mock_nitrate_stats_group,
        user=mock_user)

    # Execute fetch
    manual_cases.fetch()

    # Verify only manual non-copied cases are included
    assert len(manual_cases.stats) == 1
    assert manual_cases.stats[0] == manual_case


def test_copied_cases_fetch(
        mock_user: did.base.User,
        mock_nitrate_stats_group: NitrateStatsGroup) -> None:
    """Test CopiedCases.fetch method"""
    # Setup mock copies
    copied_case1 = Mock()
    copied_case2 = Mock()
    copies = [copied_case1, copied_case2]

    # Setup parent with mock copies
    # pylint: disable=protected-access
    mock_nitrate_stats_group._copies = copies

    # Create CopiedCases instance
    copied_cases = CopiedCases(
        option="copied",
        parent=mock_nitrate_stats_group,
        user=mock_user)

    # Execute fetch
    copied_cases.fetch()

    # Verify all copied cases are included
    assert len(copied_cases.stats) == 2
    assert copied_cases.stats == copies

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def test_nitrate_stats_group_init(
        mock_user: did.base.User) -> None:
    """Test NitrateStatsGroup initialization"""
    group = NitrateStatsGroup(
        option="nitrate", name="Nitrate Stats", user=mock_user)

    assert group.option == "nitrate"
    assert group.name == "Nitrate Stats"
    assert group.user == mock_user
    assert group.order == 100
    # pylint: disable=protected-access
    assert group._cases is None
    assert group._copies is None

    # Verify all expected stats are created
    assert len(group.stats) == 6
    stats_options = [stat.option for stat in group.stats]
    expected_options = [
        "nitrate-plans", "nitrate-runs", "nitrate-automated",
        "nitrate-manual", "nitrate-proposed", "nitrate-copied"
        ]
    assert stats_options == expected_options


@patch('did.plugins.nitrate.nitrate')
def test_nitrate_stats_group_cases_property(
        mock_nitrate: Mock,
        mock_user: did.base.User,
        mock_options: Namespace) -> None:
    """Test NitrateStatsGroup.cases property"""
    # Setup mock
    enabled_case = Mock()
    disabled_case = Mock()
    mock_status_enabled = Mock()
    mock_status_disabled = Mock()

    enabled_case.status = mock_status_enabled
    disabled_case.status = mock_status_disabled

    # Mock CaseStatus to return DISABLED for disabled case
    mock_nitrate.CaseStatus.return_value = mock_status_disabled

    mock_nitrate.TestCase.search.return_value = [
        enabled_case, disabled_case]

    # Create group
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = mock_options

    # Access cases property
    cases = group.cases

    # Verify search was called correctly
    mock_nitrate.TestCase.search.assert_called_once_with(
        author__email=mock_user.email,
        create_date__gt="2021-01-01",
        create_date__lt="2021-01-31"
        )

    # Verify CaseStatus was called to check for DISABLED
    mock_nitrate.CaseStatus.assert_called_once_with("DISABLED")

    # Verify only enabled case is returned
    assert len(cases) == 1
    assert cases[0] == enabled_case

    # Verify caching works
    cases2 = group.cases
    assert cases2 is cases
    assert mock_nitrate.TestCase.search.call_count == 1


@patch('did.plugins.nitrate.nitrate')
def test_nitrate_stats_group_copies_property(
        mock_nitrate: Mock,
        mock_user: did.base.User,
        mock_options: Namespace
        ) -> None:
    """Test NitrateStatsGroup.copies property"""
    # Setup mock
    copied_case1 = Mock()
    copied_case2 = Mock()
    mock_nitrate.TestCase.search.return_value = [copied_case1, copied_case2]

    # Create group
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = mock_options

    # Access copies property
    copies = group.copies

    # Verify search was called correctly
    mock_nitrate.TestCase.search.assert_called_once_with(
        author__email=mock_user.email,
        create_date__gt="2021-01-01",
        create_date__lt="2021-01-31",
        tag__name=TEST_CASE_COPY_TAG
        )

    # Verify all copies are returned
    assert len(copies) == 2
    assert copies == [copied_case1, copied_case2]

    # Verify caching works
    copies2 = group.copies
    assert copies2 is copies
    assert mock_nitrate.TestCase.search.call_count == 1

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Error Handling Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def test_nitrate_stats_group_cases_no_user() -> None:
    """
    Test NitrateStatsGroup.cases property
    raises error when user is None
    """
    group = NitrateStatsGroup(option="nitrate", user=None)

    with pytest.raises(ValueError, match="User is required"):
        _ = group.cases


def test_nitrate_stats_group_cases_no_options(
        mock_user: did.base.User) -> None:
    """
    Test NitrateStatsGroup.cases property
    raises error when options is None
    """
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = None

    with pytest.raises(ValueError, match="Options are required"):
        _ = group.cases


def test_nitrate_stats_group_copies_no_user() -> None:
    """
    Test NitrateStatsGroup.copies property
    raises error when user is None
    """
    group = NitrateStatsGroup(option="nitrate", user=None)

    with pytest.raises(ValueError, match="User is required"):
        _ = group.copies


def test_nitrate_stats_group_copies_no_options(
        mock_user: did.base.User) -> None:
    """
    Test NitrateStatsGroup.copies property
    raises error when options is None
    """
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = None

    with pytest.raises(ValueError, match="Options are required"):
        _ = group.copies

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Integration Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@patch('did.plugins.nitrate.nitrate')
def test_nitrate_stats_group_integration(
        mock_nitrate: Mock,
        mock_user: did.base.User,
        mock_options: Namespace) -> None:
    """
    Test integration between NitrateStatsGroup
    and individual stats
    """
    # Setup mock data
    mock_case1 = Mock()
    mock_case1.automated = True
    mock_case1.autoproposed = False

    mock_case2 = Mock()
    mock_case2.automated = False
    mock_case2.autoproposed = True

    mock_copied_case = Mock()
    mock_copied_case.automated = False
    mock_copied_case.autoproposed = False

    # Mock the disabled status check
    mock_status_enabled = Mock()
    mock_status_disabled = Mock()
    mock_case1.status = mock_status_enabled
    mock_case2.status = mock_status_enabled
    mock_copied_case.status = mock_status_enabled

    mock_nitrate.CaseStatus.return_value = mock_status_disabled

    # Setup search results
    all_cases = [mock_case1, mock_case2, mock_copied_case]
    copied_cases = [mock_copied_case]

    mock_nitrate.TestCase.search.side_effect = [all_cases, copied_cases]

    # Create group
    group = NitrateStatsGroup(option="nitrate", user=mock_user)
    group.options = mock_options

    # Test individual stats
    automated_stats = group.stats[2]  # AutomatedCases
    automated_stats.fetch()
    assert len(automated_stats.stats) == 1
    assert automated_stats.stats[0] == mock_case1

    manual_stats = group.stats[3]  # ManualCases
    manual_stats.fetch()
    assert len(manual_stats.stats) == 1
    assert manual_stats.stats[0] == mock_case2

    autoproposed_stats = group.stats[4]  # AutoproposedCases
    autoproposed_stats.fetch()
    assert len(autoproposed_stats.stats) == 1
    assert autoproposed_stats.stats[0] == mock_case2

    copied_stats = group.stats[5]  # CopiedCases
    copied_stats.fetch()
    assert len(copied_stats.stats) == 1
    assert copied_stats.stats[0] == mock_copied_case


def test_constant_test_case_copy_tag() -> None:
    """Test that TEST_CASE_COPY_TAG constant is properly defined"""
    assert TEST_CASE_COPY_TAG == "TestCaseCopy"
