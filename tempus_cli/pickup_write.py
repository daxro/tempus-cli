"""Source-proven Home API pickup assignments and durable single-attempt saves."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from filelock import FileLock, Timeout

from .errors import SafetyError
from .paths import repo_root

SCHEDULE_FIELDS = {'date', 'scheduleTimes', 'message', 'pickupId', 'arrivingAlone', 'departingAlone'}
TIME_FIELDS = {'startTime', 'stopTime', 'enrollmentId'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def verification_state(raw):
    # The app omits server scheduleTimeId; the live API regenerates it on POST.
    state = deepcopy(raw)
    for span in state.get('scheduleTimes', []):
        span.pop('scheduleTimeId', None)
    return state


def field_fingerprints(value, prefix=''):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(field_fingerprints(child, f'{prefix}.{key}' if prefix else key))
        return result
    if isinstance(value, list) and value:
        result = {}
        for index, child in enumerate(value):
            result.update(field_fingerprints(child, f'{prefix}[{index}]'))
        return result
    return {prefix: fingerprint(value)}


def positive_id(value):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal() or int(value) <= 0:
        raise ValueError('pickup and child IDs must be positive decimal IDs')
    return int(value)


def pickup_body(raw, child_id, day, pickup_id):
    """Mirror app 3.43.4 createPayload; refuse fields with unknown preservation semantics."""
    positive_id(child_id)
    positive_id(pickup_id)
    if not isinstance(raw, dict) or set(raw) - SCHEDULE_FIELDS - {'childId'}:
        raise ValueError('unsupported schedule fields; refusing to risk changing them')
    if not SCHEDULE_FIELDS <= raw.keys() or raw['date'] != day or str(raw.get('childId')) != str(child_id):
        raise ValueError('schedule did not match the requested child/date or missed required fields')
    if not isinstance(raw['arrivingAlone'], bool) or not isinstance(raw['departingAlone'], bool):
        raise ValueError('schedule alone flags must be booleans')
    if raw['departingAlone']:
        raise ValueError('departing-alone schedule cannot keep its flags and assign a pickup person')
    if raw['message'] is not None and not isinstance(raw['message'], str):
        raise ValueError('schedule message had an unsupported shape')
    date.fromisoformat(day)
    if not isinstance(raw['scheduleTimes'], list):
        raise ValueError('schedule times had an unsupported shape')
    times = []
    for span in raw['scheduleTimes']:
        if not isinstance(span, dict) or set(span) - TIME_FIELDS - {'scheduleTimeId'} or not TIME_FIELDS <= span.keys():
            raise ValueError('unsupported schedule time fields; refusing to risk changing them')
        start, stop = span['startTime'], span['stopTime']
        if any(type(t) is not int for t in (start, stop)) or not 0 <= start < stop <= 1439:
            raise ValueError('schedule times must be minutes within a day; refusing to alter times')
        positive_id(span['enrollmentId'])
        times.append({key: deepcopy(span[key]) for key in ('startTime', 'stopTime', 'enrollmentId')})
    schedule = {key: deepcopy(raw[key]) for key in ('date', 'message', 'arrivingAlone', 'departingAlone')}
    schedule['scheduleTimes'] = times
    schedule['pickupId'] = positive_id(pickup_id)
    return [{'childId': positive_id(child_id), 'schedules': [schedule]}]


def validate_body(body):
    if not isinstance(body, list) or len(body) != 1 or not isinstance(body[0], dict) or set(body[0]) != {'childId', 'schedules'}:
        raise ValueError('pickup POST must contain exactly one child')
    child = body[0]
    if not isinstance(child['schedules'], list) or len(child['schedules']) != 1:
        raise ValueError('pickup POST must contain exactly one date')
    row = child['schedules'][0]
    if not isinstance(row, dict) or set(row) != SCHEDULE_FIELDS:
        raise ValueError('pickup POST contained unsupported schedule fields')
    rebuilt = pickup_body({**row, 'childId': child['childId']}, child['childId'], row['date'], row['pickupId'])
    if body != rebuilt:
        raise ValueError('pickup POST did not match the verified request contract')


def editability(raw, context, day, child_id, *, today=None):
    """Use fresh refreshCalendar children/departments/events; fail closed on ambiguous metadata."""
    today = today or datetime.now(ZoneInfo('Europe/Stockholm')).date()
    requested = date.fromisoformat(day)
    if requested < today:
        return 'past_date', {}
    if not isinstance(context, dict) or not all(key in context for key in ('children', 'departments', 'calendarEvents')):
        return 'editability_metadata_unavailable', {}
    if not isinstance(context['children'], list) or not isinstance(context['departments'], list):
        return 'editability_metadata_unavailable', {}
    if not all(isinstance(row, dict) for row in context['children'] + context['departments']):
        return 'editability_metadata_unavailable', {}
    children = [c for c in context['children'] if str(c.get('childId')) == str(child_id)]
    if len(children) != 1:
        return 'editability_metadata_ambiguous', {}
    enrollments = children[0].get('enrollments')
    if not isinstance(enrollments, list):
        return 'editability_metadata_unavailable', {}
    if not all(isinstance(e, dict) for e in enrollments):
        return 'editability_metadata_unavailable', {}
    for enrollment in enrollments:
        for key in ('enrollmentStart', 'enrollmentStop'):
            if enrollment.get(key) is not None:
                try:
                    date.fromisoformat(enrollment[key])
                except (TypeError, ValueError):
                    return 'editability_metadata_unavailable', {}
    active = [e for e in enrollments if (e.get('enrollmentStart') or '0001-01-01') <= day <= (e.get('enrollmentStop') or '9999-12-31')]
    time_ids = {str(t.get('enrollmentId')) for t in raw.get('scheduleTimes', [])}
    selected = [e for e in active if not time_ids or str(e.get('enrollmentId')) in time_ids]
    if not selected or time_ids - {str(e.get('enrollmentId')) for e in selected}:
        return 'schedule_enrollment_unavailable', {}
    department_ids = {str(e.get('departmentId')) for e in selected}
    departments = [d for d in context['departments'] if str(d.get('departmentId')) in department_ids]
    if {str(d.get('departmentId')) for d in departments} != department_ids:
        return 'department_metadata_unavailable', {}
    events_wrapper = context['calendarEvents']
    events = events_wrapper.get('calendarEvents') if isinstance(events_wrapper, dict) else None
    if not isinstance(events, list):
        return 'editability_metadata_unavailable', {}
    relevant = []
    for event in events:
        if not isinstance(event, dict):
            return 'editability_metadata_unavailable', {}
        start, stop = event.get('startDate'), event.get('stopDate')
        if not isinstance(start, str) or not isinstance(stop, str):
            return 'event_dates_unavailable', {}
        try:
            date.fromisoformat(start)
            date.fromisoformat(stop)
        except ValueError:
            return 'event_dates_unavailable', {}
        if start > stop:
            return 'event_dates_unavailable', {}
        if not start <= day <= stop:
            continue
        ids = event.get('departmentIds')
        if not isinstance(ids, list) or (not ids and (event.get('locked') or event.get('scheduleFreezeDate'))):
            return 'event_departments_unavailable', {}
        if department_ids & {str(v) for v in ids}:
            relevant.append(event)
    state = deepcopy({'enrollments': selected, 'departments': departments, 'events': relevant, 'today': today.isoformat()})
    for department in departments:
        days = department.get('lateScheduleLockedDays') or 0
        if type(days) is not int or days < 0:
            return 'editability_metadata_unavailable', state
        if days > 0 and (requested - today).days < days:
            return 'late_schedule_locked', state
    for event in relevant:
        if event.get('locked'):
            return 'calendar_event_locked', state
        freeze = event.get('scheduleFreezeDate')
        if freeze and (not event.get('freezeOnlyOnLeave') or not raw.get('scheduleTimes')):
            try:
                frozen = date.fromisoformat(freeze) <= today
            except (TypeError, ValueError):
                return 'editability_metadata_unavailable', state
            if frozen:
                # Blocking intersecting intervals is deliberately conservative.
                return 'calendar_event_frozen', state
    return None, state


def preview_token(assignment, contact):
    return fingerprint({'assignment': assignment, 'contact': contact})


def _save_journal(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pickup-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_assignment(api, assignment, contact, token, journal_path):
    """Serialize saves, write durable intent first, POST once, then verify every raw field."""
    path = Path(journal_path).resolve()
    if path.is_relative_to(repo_root()):
        raise SafetyError('Refusing to store pickup attempt state inside repository')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(path) + '.lock', timeout=15):
            try:
                journal = json.loads(path.read_text()) if path.exists() else {'version': 1, 'attempts': {}}
                if journal.get('version') != 1 or not isinstance(journal.get('attempts'), dict):
                    raise ValueError()
                for record in journal['attempts'].values():
                    if (not isinstance(record, dict) or record.get('state') not in ('pending', 'verified')
                            or not isinstance(record.get('expected'), str) or len(record['expected']) != 64
                            or record.get('verification') not in (None, 'schedule_values')):
                        raise ValueError()
            except (OSError, ValueError, AttributeError) as exc:
                raise SafetyError('Pickup attempt state is unreadable; refusing a possible duplicate write') from exc
            key = fingerprint([assignment['child_id'], assignment['date']])
            pending = journal['attempts'].get(key)
            current = api.pickup_assignment(assignment['date'], assignment['child_id'])
            if pending and pending.get('state') == 'pending':
                if fingerprint(verification_state(current['_raw']) if pending.get('verification') == 'schedule_values' else current['_raw']) == pending.get('expected'):
                    pending['state'] = 'verified'
                    _save_journal(path, journal)
                    if str(current.get('pickup_id')) == str(contact['id']):
                        return {'write_performed': False, 'reconciled': True, 'verification': {'matched': True}, 'assignment': current}
                else:
                    raise SafetyError('Previous pickup save has an uncertain result; inspect the assignment and reconcile before another save. No POST was sent')
            contacts = api.pickups()
            matches = [c for c in contacts if str(c.get('id')) == str(contact['id'])]
            if len(matches) != 1:
                raise ValueError('pickup contact changed since preview; re-run preview')
            if preview_token(current, matches[0]) != token or preview_token(assignment, contact) != token:
                raise ValueError('pickup assignment or contact changed since preview; re-run preview')
            if current.get('block_reason') or not current.get('write_supported'):
                raise ValueError('pickup assignment is blocked: ' + str(current.get('block_reason')))
            if str(current.get('pickup_id')) == str(contact['id']):
                return {'write_performed': False, 'no_op': True, 'verification': {'matched': True}, 'assignment': current}
            body = pickup_body(current['_raw'], current['child_id'], current['date'], contact['id'])
            expected = deepcopy(current['_raw'])
            expected['pickupId'] = positive_id(contact['id'])
            journal['attempts'][key] = {'state': 'pending', 'expected': fingerprint(verification_state(expected)),
                                       'verification': 'schedule_values',
                                       'fields': field_fingerprints(verification_state(expected))}
            _save_journal(path, journal)
            uncertain = False
            try:
                api._post_pickup(body)
            except Exception:
                # Do not replay, expose server payloads, or trust the HTTP response as proof of the save.
                uncertain = True
            try:
                verified = api.pickup_assignment(current['date'], current['child_id'])
                matched = fingerprint(verification_state(verified['_raw'])) == fingerprint(verification_state(expected))
            except Exception:
                verified, matched = None, False
            changed_fields = []
            if verified is not None:
                expected_fields = field_fingerprints(verification_state(expected))
                actual_fields = field_fingerprints(verification_state(verified['_raw']))
                changed_fields = sorted(key for key in expected_fields.keys() | actual_fields.keys()
                                        if expected_fields.get(key) != actual_fields.get(key))
            if matched:
                journal['attempts'][key]['state'] = 'verified'
                _save_journal(path, journal)
            return {'write_performed': True if matched else None, 'write_attempted': True, 'outcome': 'verified' if matched else 'uncertain',
                    'response_uncertain': uncertain, 'verification': {'matched': matched, 'changed_fields': changed_fields}, 'assignment': verified}
    except Timeout as exc:
        raise SafetyError('Another pickup save is in progress; no POST was sent') from exc
