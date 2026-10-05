from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest
import requests

from tempus_cli.errors import SafetyError
from tempus_cli.home_client import HomeTempusApi
from tempus_cli.pickup_write import apply_assignment, editability, pickup_body, preview_token

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/home_api/pickup_write.json').read_text())
DAY = '2027-01-05'
TODAY = date(2027, 1, 5)


class FakeApi(HomeTempusApi):
    def __init__(self):
        self.context = deepcopy(FIXTURE['read_before'])
        self.contact = deepcopy(FIXTURE['contact'])
        self.writes = []
        self.after_post = None
        self.fail_reads = False
    def refresh_calendar(self, start, stop):
        assert start == stop == DAY
        if self.fail_reads:
            raise RuntimeError('generated read failure')
        return deepcopy(self.context)
    def pickups(self):
        return [deepcopy(self.contact)]
    @property
    def raw(self):
        return self.context['schedules']['schedules'][0]['schedules'][0]
    def _post_pickup(self, body):
        self.writes.append(deepcopy(body))
        if self.after_post:
            self.after_post(self)
        else:
            self.raw['pickupId'] = 202


def snapshot(api):
    assignment = api.pickup_assignment(DAY, '101')
    contact = deepcopy(api.contact)
    return assignment, contact, preview_token(assignment, contact)


def apply(api, path, state=None):
    assignment, contact, token = state or snapshot(api)
    return apply_assignment(api, assignment, contact, token, path)


def test_request_matches_source_derived_fixture_and_preserves_read_fields(tmp_path):
    api = FakeApi()
    before = deepcopy(api.raw)
    result = apply(api, tmp_path / 'journal.json')
    assert api.writes == [FIXTURE['request']['body']]
    expected = {**before, 'pickupId': 202}
    assert api.raw == expected
    assert result['verification'] == {'matched': True, 'changed_fields': []}
    assert result['write_performed'] is True
    assert (tmp_path / 'journal.json').stat().st_mode & 0o777 == 0o600
    text = (tmp_path / 'journal.json').read_text()
    assert 'Generated' not in text and DAY not in text
    assert 'Generated message' not in text


def test_duplicate_apply_sends_no_second_post(tmp_path):
    api = FakeApi()
    apply(api, tmp_path / 'journal.json')
    result = apply(api, tmp_path / 'journal.json')
    assert len(api.writes) == 1
    assert result['write_performed'] is False
    assert result['no_op'] is True


@pytest.mark.parametrize('change', ['message', 'time', 'flag', 'contact', 'freeze', 'enrollment'])
def test_state_change_since_reviewed_preview_never_posts(tmp_path, change):
    api = FakeApi()
    state = snapshot(api)
    if change == 'message':
        api.raw['message'] = 'Generated changed message'
    elif change == 'time':
        api.raw['scheduleTimes'][0]['stopTime'] = 930
    elif change == 'flag':
        api.raw['arrivingAlone'] = False
    elif change == 'contact':
        api.contact['name'] = 'Generated changed contact'
    elif change == 'freeze':
        api.context['departments'][0]['lateScheduleLockedDays'] = 365
    else:
        api.context['children'][0]['enrollments'][0]['enrollmentStop'] = '2026-12-31'
    with pytest.raises(ValueError, match='changed since preview'):
        apply(api, tmp_path / 'journal.json', state)
    assert api.writes == []


@pytest.mark.parametrize('behavior', ['timeout_saved', 'timeout_not_saved', 'malformed', 'read_failure', 'other_field'])
def test_uncertain_result_readback_and_new_process_do_not_retry(tmp_path, behavior):
    api = FakeApi()
    def after_post(api):
        if behavior in ('timeout_saved', 'other_field', 'read_failure'):
            api.raw['pickupId'] = 202
        if behavior == 'other_field':
            api.raw['message'] = 'Generated unexpected change'
        if behavior == 'read_failure':
            api.fail_reads = True
        if behavior.startswith('timeout'):
            raise requests.Timeout('generated timeout')
        if behavior == 'malformed':
            raise RuntimeError('generated malformed response')
    api.after_post = after_post
    path = tmp_path / 'journal.json'
    result = apply(api, path)
    assert len(api.writes) == 1
    assert result['verification']['matched'] is (behavior == 'timeout_saved')
    restarted = FakeApi()
    restarted.context = deepcopy(api.context)
    if behavior in ('timeout_not_saved', 'malformed', 'other_field'):
        with pytest.raises(SafetyError, match='uncertain result'):
            apply(restarted, path)
    else:
        reconciled = apply(restarted, path)
        assert reconciled['verification']['matched'] is True
        assert reconciled['write_performed'] is False
    assert restarted.writes == []
    assert len(api.writes) == 1


def test_concurrent_applies_make_one_post(tmp_path):
    api = FakeApi()
    state = snapshot(api)
    path = tmp_path / 'journal.json'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(apply, api, path, state) for _ in range(2)]
    outcomes = []
    for result in results:
        try:
            outcomes.append(result.result())
        except ValueError as exc:
            assert 'changed since preview' in str(exc)
    assert len(api.writes) == 1
    assert any(r['verification']['matched'] for r in outcomes)


def test_journal_failure_prevents_post(tmp_path, monkeypatch):
    api = FakeApi()
    from tempus_cli import pickup_write
    monkeypatch.setattr(pickup_write, '_save_journal', lambda *args: (_ for _ in ()).throw(OSError('generated failure')))
    with pytest.raises(OSError):
        apply(api, tmp_path / 'journal.json')
    assert api.writes == []


def test_corrupt_journal_prevents_post(tmp_path):
    path = tmp_path / 'journal.json'
    path.write_text('invalid')
    api = FakeApi()
    with pytest.raises(SafetyError, match='unreadable'):
        apply(api, path)
    assert api.writes == []


@pytest.mark.parametrize('change', ['unknown_schedule', 'unknown_time', 'departing_alone', 'milliseconds', 'midnight'])
def test_unsupported_preservation_never_enables_writes(change):
    api = FakeApi()
    if change == 'unknown_schedule':
        api.raw['unverifiedField'] = 'generated'
    elif change == 'unknown_time':
        api.raw['scheduleTimes'][0]['unverifiedField'] = 'generated'
    elif change == 'departing_alone':
        api.raw['departingAlone'] = True
    elif change == 'milliseconds':
        api.raw['scheduleTimes'][0]['stopTime'] = 57600000
    else:
        api.raw['scheduleTimes'][0]['stopTime'] = 1440
    assert snapshot(api)[0]['write_supported'] is False


def test_multiple_schedule_times_enrollments_are_preserved(tmp_path):
    api = FakeApi()
    api.raw['scheduleTimes'].append({'scheduleTimeId': 402, 'enrollmentId': 602, 'startTime': 970, 'stopTime': 1000})
    api.context['children'][0]['enrollments'].append({'enrollmentId': 602, 'departmentId': 702,
                                                   'enrollmentStart': '2025-01-01', 'enrollmentStop': '2030-12-31'})
    api.context['departments'].append({'departmentId': 702, 'lateScheduleLockedDays': 0})
    assert apply(api, tmp_path / 'journal.json')['verification']['matched'] is True
    assert len(api.writes[0][0]['schedules'][0]['scheduleTimes']) == 2


@pytest.mark.parametrize('field', ['locked', 'scheduleFreezeDate'])
def test_frozen_and_locked_calendar_events_block(field):
    api = FakeApi()
    event = {'startDate': DAY, 'stopDate': DAY, 'departmentIds': [701], 'freezeOnlyOnLeave': False}
    event[field] = True if field == 'locked' else '2027-01-04'
    api.context['calendarEvents']['calendarEvents'] = [event]
    reason, _ = editability({**api.raw, 'childId': 101}, api.context, DAY, '101', today=TODAY)
    assert reason in ('calendar_event_locked', 'calendar_event_frozen')


def test_on_leave_only_freeze_does_not_freeze_existing_schedule():
    api = FakeApi()
    api.context['calendarEvents']['calendarEvents'] = [{
        'startDate': DAY, 'stopDate': DAY, 'departmentIds': [701],
        'scheduleFreezeDate': '2027-01-04', 'freezeOnlyOnLeave': True,
    }]
    assert editability(api.raw, api.context, DAY, '101', today=TODAY)[0] is None


def test_late_lock_uses_only_current_schedule_enrollment():
    api = FakeApi()
    api.context['children'][0]['enrollments'].append({'enrollmentId': 602, 'departmentId': 702,
                                                   'enrollmentStart': '2025-01-01', 'enrollmentStop': '2025-12-31'})
    api.context['departments'].append({'departmentId': 702, 'lateScheduleLockedDays': 365})
    assert editability(api.raw, api.context, DAY, '101', today=TODAY)[0] is None


@pytest.fixture(autouse=True)
def freeze_test_today(monkeypatch):
    from tempus_cli import home_client
    monkeypatch.setattr(home_client, 'editability',
                        lambda raw, context, day, child: editability(raw, context, day, child, today=TODAY))


def test_conflicting_rows_with_same_pickup_are_rejected():
    api = FakeApi()
    extra = deepcopy(api.raw)
    extra['message'] = 'Generated conflicting message'
    api.context['schedules']['schedules'][0]['schedules'].append(extra)
    with pytest.raises(RuntimeError, match='conflicting'):
        snapshot(api)


def test_read_deduplicates_one_schedule_split_into_departments():
    api = FakeApi()
    api.context['children'][0]['enrollments'].append({'enrollmentId': 602, 'departmentId': 702,
                                                   'enrollmentStart': '2025-01-01', 'enrollmentStop': '2030-12-31'})
    api.context['departments'].append({'departmentId': 702, 'lateScheduleLockedDays': 0})
    api.raw['scheduleTimes'].append({'enrollmentId': 602, 'scheduleTimeId': 402, 'startTime': 970, 'stopTime': 1000})
    assert snapshot(api)[0]['write_supported'] is True


def test_cli_preview_then_apply_and_stale_token(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli
    api = FakeApi()
    api.token_path = tmp_path / 'session.json'
    api.children_and_notifications = lambda: [{'id': '101', 'name': 'Generated Child'}]
    monkeypatch.setattr(cli, '_get_authenticated_api', lambda no_input=False: api)
    args = ['pickup', '--date', DAY, '--child', 'Generated Child', '--id', '202', '--json', '--no-input']
    assert cli.main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview['contact']['name'] == 'Generated Proposed Guardian'
    assert preview['existing_assignment']['pickup_id'] == '201'
    assert preview['write_performed'] is False
    assert cli.main(args + ['--apply', '--confirm', '--preview-token', preview['preview_token']]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved['verification'] == {'matched': True, 'changed_fields': []}
    assert saved['verified_assignment']['pickup_id'] == '202'
    assert len(api.writes) == 1
    assert cli.main(args + ['--apply', '--confirm', '--preview-token', preview['preview_token']]) == 2
    assert 'changed since preview' in capsys.readouterr().err
    assert len(api.writes) == 1


def test_cli_uncertain_save_returns_json_failure_without_raw_server_error(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli
    api = FakeApi()
    api.token_path = tmp_path / 'session.json'
    api.children_and_notifications = lambda: [{'id': '101', 'name': 'Generated Child'}]
    api.after_post = lambda api: (_ for _ in ()).throw(RuntimeError('generated private server detail'))
    monkeypatch.setattr(cli, '_get_authenticated_api', lambda no_input=False: api)
    args = ['pickup', '--date', DAY, '--child', 'Generated Child', '--id', '202', '--json']
    assert cli.main(args) == 0
    token = json.loads(capsys.readouterr().out)['preview_token']
    assert cli.main(args + ['--apply', '--confirm', '--preview-token', token]) == 1
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data['outcome'] == 'uncertain'
    assert data['verification']['matched'] is False
    assert data['write_performed'] is None
    assert data['write_attempted'] is True
    assert 'private server' not in output.out + output.err


def test_open_ended_enrollment_is_supported():
    api = FakeApi()
    api.context['children'][0]['enrollments'][0]['enrollmentStop'] = None
    assert snapshot(api)[0]['write_supported'] is True


def test_server_regenerated_time_id_does_not_hide_schedule_changes(tmp_path):
    api = FakeApi()
    def server(api):
        api.raw['pickupId'] = 202
        api.raw['scheduleTimes'][0]['scheduleTimeId'] = 402
    api.after_post = server
    result = apply(api, tmp_path / 'journal.json')
    assert result['verification'] == {'matched': True, 'changed_fields': []}
    assert api.raw['scheduleTimes'][0]['scheduleTimeId'] == 402
    assert len(api.writes) == 1
    assert apply(api, tmp_path / 'journal.json')['write_performed'] is False


def test_unknown_old_receipt_is_not_silently_relaxed(tmp_path):
    from tempus_cli.pickup_write import fingerprint
    api = FakeApi()
    raw = {**api.raw, 'childId': 101, 'pickupId': 202}
    path = tmp_path / 'journal.json'
    path.write_text(json.dumps({'version': 1, 'attempts': {
        fingerprint(['101', DAY]): {'state': 'pending', 'expected': fingerprint(raw)},
    }}))
    api.raw['pickupId'] = 202
    api.raw['scheduleTimes'][0]['scheduleTimeId'] = 402
    with pytest.raises(SafetyError, match='uncertain result'):
        apply(api, path)
    assert api.writes == []


def test_saved_assignment_with_changed_time_is_not_verified(tmp_path):
    api = FakeApi()
    def server(api):
        api.raw['pickupId'] = 202
        api.raw['scheduleTimes'][0]['scheduleTimeId'] = 402
        api.raw['scheduleTimes'][0]['stopTime'] = 930
    api.after_post = server
    result = apply(api, tmp_path / 'journal.json')
    assert result['verification']['matched'] is False
    assert result['verification']['changed_fields'] == ['scheduleTimes[0].stopTime']
    with pytest.raises(SafetyError, match='uncertain result'):
        apply(api, tmp_path / 'journal.json')
    assert len(api.writes) == 1


def test_interrupted_save_remains_pending_without_retry(tmp_path):
    api = FakeApi()
    api.after_post = lambda api: (_ for _ in ()).throw(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        apply(api, tmp_path / 'journal.json')
    with pytest.raises(SafetyError, match='uncertain result'):
        apply(api, tmp_path / 'journal.json')
    assert len(api.writes) == 1


@pytest.mark.parametrize('key,value', [('children', {}), ('departments', [None]),
                                      ('calendarEvents', {'calendarEvents': [None]})])
def test_invalid_editability_metadata_fails_closed(key, value):
    api = FakeApi()
    api.context[key] = value
    assert snapshot(api)[0]['write_supported'] is False


def test_invalid_enrollment_dates_fail_closed():
    api = FakeApi()
    api.context['children'][0]['enrollments'][0]['enrollmentStart'] = 123
    assert snapshot(api)[0]['write_supported'] is False


def test_incomplete_event_dates_fail_closed():
    api = FakeApi()
    api.context['calendarEvents']['calendarEvents'] = [{'startDate': 'invalid', 'stopDate': DAY, 'departmentIds': [701], 'locked': True}]
    assert snapshot(api)[0]['write_supported'] is False


def test_corrupt_nested_receipt_prevents_post(tmp_path):
    path = tmp_path / 'journal.json'
    path.write_text(json.dumps({'version': 1, 'attempts': {'generated-key': 'invalid'}}))
    api = FakeApi()
    with pytest.raises(SafetyError, match='unreadable'):
        apply(api, path)
    assert api.writes == []


def test_verified_live_fixture_preserves_all_editable_values():
    from tempus_cli.pickup_write import verification_state
    from tempus_cli.pickup_fixtures import assert_sanitized_fixture
    data = json.loads((Path(__file__).parent / 'fixtures/home_api/pickup_write_live_shape.json').read_text())
    assert_sanitized_fixture(data)
    before, after = data['read_before'], data['read_after']
    expected = {**before, 'pickupId': 202}
    assert verification_state(expected) == verification_state(after)
    assert before['scheduleTimes'][0]['scheduleTimeId'] != after['scheduleTimes'][0]['scheduleTimeId']
    assert pickup_body(before, '101', DAY, '202') == data['request']['body']


def test_schedule_read_displays_verified_minute_values():
    from tempus_cli.home_client import normalize_schedules
    data = deepcopy(FIXTURE['read_before'])
    assert normalize_schedules(data)[0]['times'] == [{'start': '08:00', 'stop': '16:00'}]
