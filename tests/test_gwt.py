import pytest
import json
from pathlib import Path

from tempus_cli.gwt import (
    parse_assignment_write_response,
    parse_children_and_notifications,
    parse_identity_providers,
    parse_pickup_assignment,
    parse_pickups,
    parse_schemas,
    parse_week_schedule_assignment,
    payload_assign_pickup_for_date,
    payload_authenticate_user_with_cookies,
    payload_get_children_and_notifications,
    payload_get_pickup_date_assignment,
    payload_get_grand_id_identity_providers,
    payload_get_pickups,
    payload_get_schemas,
    payload_get_week_schedules,
    payload_heartbeat,
    payload_remove_pickup,
    payload_update_schedule_assignment,
)

SCHEMAS = '//OK[14,938,13,2,12,727,11,2,10,399,9,2,8,275,7,2,6,23,5,2,4,20,3,2,6,1,["java.util.ArrayList/4159755760","se.tempus.common.shared.wrapper.Schema/2582274289","Sandsborgs Montessori","tempus-sandsborgsm","Miro Kids","tempus-stockholm-miro-kids","Katarina Barnstugeförening","tempus-stockholm-katarina","Stockholms stad","tempus-stockholm","Framtidsfolket Cosmos","tempus-stockholm-framtidsfolket","Stockholms stad OB","tempus-stockholm-ob"],0,7]'
PROVIDERS = '//OK[0,3,5,4,3,0,2,1,1,["java.util.ArrayList/4159755760","se.tempus.common.shared.grandid.SelectableGrandIdIdp/2371313207","Stockholm-inlogg","se.tempus.common.shared.login.LoginOption/2533300465","STOCKHOLM_PROD"],0,7]'
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pickup_date_assignment"


def _fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _normalize_permutation(payload):
    return payload.replace("|P|", "|PERMUTATION|")


def test_payloads_match_observed_shape():
    assert payload_get_schemas("P", 12) == '7|0|5|https://home.tempusinfo.se/tempusHome/tempusHome/|P|se.limesaudio.tempushome.client.HomeService|getSchemas|I|1|2|3|4|1|5|12|'
    assert "getGrandIdIdentityProviders" in payload_get_grand_id_identity_providers("P", 399)
    assert "getPickups" in payload_get_pickups("P")
    assert payload_heartbeat("P") == '7|0|4|https://home.tempusinfo.se/tempusHome/tempusHome/|P|se.limesaudio.tempushome.client.HomeService|heartbeat|1|2|3|4|0|'
    assert "removePickup" in payload_remove_pickup("P", 123)


def test_authenticate_user_with_cookies_payload_matches_observed_shape():
    assert payload_authenticate_user_with_cookies("P") == (
        "7|0|5|https://home.tempusinfo.se/tempusHome/tempusHome/|P|"
        "se.limesaudio.tempushome.client.HomeService|authenticateUserWithCookies|Z|"
        "1|2|3|4|2|5|5|0|0|"
    )
    assert payload_authenticate_user_with_cookies("P", use_nu_cookie=True, use_bearer_auth=True).endswith("|1|1|")


def test_assignment_read_payload_matches_fixture_bytes():
    fixture = _fixture("read_before.json")
    payload = payload_get_pickup_date_assignment("P", "2026-06-11", 101)
    assert _normalize_permutation(payload) == fixture["request_payload"]


def test_children_and_notifications_payload_matches_fixture_bytes():
    fixture = _fixture("children_and_notifications.json")
    payload = payload_get_children_and_notifications("P")
    assert _normalize_permutation(payload) == fixture["request_payload"]


def test_week_schedules_payload_matches_fixture_bytes():
    fixture = _fixture("week_schedules.json")
    payload = payload_get_week_schedules("P", [(2026, 24)])
    assert _normalize_permutation(payload) == fixture["request_payload"]


def test_assignment_write_payload_matches_fixture_bytes():
    fixture = _fixture("update_schedule_assignment.json")
    payload = payload_update_schedule_assignment(
        "P",
        {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "123",
            "pickup_name": "Generated Pickup",
            "pickup_phone": "0700000000",
            "owner_name": "Generated Owner",
            "pickup_child_ids": ["101", "102", "103"],
            "schedule_id": "901",
            "start_ms": "28800000",
            "end_ms": "59400000",
        },
    )
    assert _normalize_permutation(payload) == fixture["request_payload"]


def test_assignment_fixture_documents_method_arguments_and_fields():
    read_fixture = _fixture("read_before.json")
    write_fixture = _fixture("update_schedule_assignment.json")
    schedule_fixture = _fixture("week_schedules.json")
    assert read_fixture["gwt_rpc_method"] == "getPickupDateAssignment"
    assert read_fixture["argument_order"] == ["date", "child_id"]
    assert read_fixture["date_representation"] == "YYYY-MM-DD string"
    assert read_fixture["child_id_source"] == "pickup child row id from getPickups response"
    assert schedule_fixture["gwt_rpc_method"] == "getWeekSchedules"
    assert schedule_fixture["argument_order"] == ["weeks"]
    assert write_fixture["gwt_rpc_method"] == "updateSchedule"
    assert write_fixture["argument_order"] == [
        "child_id",
        "date",
        "day_schedule",
    ]
    assert "schedule_id" in write_fixture["required_write_fields"]


def test_parse_schemas():
    rows = parse_schemas(SCHEMAS)
    assert {r["name"]: r["id"] for r in rows}["Stockholms stad"] == 399


def test_parse_identity_providers():
    assert parse_identity_providers(PROVIDERS) == [{"name":"Stockholm-inlogg", "option":"STOCKHOLM_PROD"}]


def test_parse_pickups_from_sanitized_fixture():
    response = '//OK[{"pickups":[{"pickupId":123,"name":"Example Guardian","phoneNumber":"0700000000","children":["Example Child"],"version":"opaque"}]}]'
    assert parse_pickups(response) == [
        {
            "id": "123",
            "name": "Example Guardian",
            "phone": "0700000000",
            "children": ["Example Child"],
            "_raw": {
                "pickupId": 123,
                "name": "Example Guardian",
                "phoneNumber": "0700000000",
                "children": ["Example Child"],
                "version": "opaque",
            },
        }
    ]


def test_parse_pickups_from_encoded_tree_set_fixture():
    strings = [
        "java.util.TreeSet/4043497002",
        "se.tempus.common.shared.wrapper.Pickup/873253356",
        "java.util.ArrayList/4159755760",
        "java.lang.Integer/3438268394",
        "Example Child A",
        "Example Guardian A",
        "Example Child B",
        "Example Guardian B",
        "0700000000",
        "",
    ]
    response = (
        "//OK"
        + repr(
            [
                0,
                0,
                10,
                6,
                123,
                5,
                456,
                4,
                789,
                4,
                1,
                3,
                2,
                0,
                0,
                9,
                8,
                124,
                7,
                457,
                4,
                789,
                4,
                1,
                3,
                2,
                2,
                0,
                1,
                strings,
                0,
                7,
            ]
        ).replace("'", '"')
    )

    assert parse_pickups(response) == [
        {
            "id": "123",
            "name": "Example Guardian A",
            "phone": None,
            "children": ["Example Child A"],
                "_raw": {
                    "encoded": [10, 6, 123, 5, 456, 4, 789, 4, 1, 3, 2],
                    "children": [{"name": "Example Child A", "id": "456"}],
                    "owner_name": "Example Child A",
                    "pickup_child_ids": ["456", "789"],
                },
            },
        {
            "id": "124",
            "name": "Example Guardian B",
            "phone": "0700000000",
            "children": ["Example Child B"],
                "_raw": {
                    "encoded": [9, 8, 124, 7, 457, 4, 789, 4, 1, 3, 2],
                    "children": [{"name": "Example Child B", "id": "457"}],
                    "owner_name": "Example Child B",
                    "pickup_child_ids": ["457", "789"],
                },
            },
    ]


def test_parse_pickups_empty_list():
    assert parse_pickups("//OK[]") == []


def test_parse_pickups_fails_closed_for_non_ok_response():
    with pytest.raises(RuntimeError, match="not a successful"):
        parse_pickups("<html>login</html>")


def test_parse_pickups_fails_closed_for_unrecognized_gwt_shape():
    with pytest.raises(RuntimeError, match="recognized pickup data"):
        parse_pickups('//OK[1,2,["java.util.ArrayList/4159755760"],0,7]')


def test_parse_assignment_read_before_fixture():
    fixture = _fixture("read_before.json")
    assert parse_pickup_assignment(fixture["response_body"]) == {
        "date": "2026-06-11",
        "child_id": "101",
        "child_name": "Generated Child",
        "pickup_id": "456",
        "pickup_name": "Generated Pickup Before",
        "assignment_id": "901",
        "version": "assignment-version-before",
        "write_token": "assignment-write-token-before",
    }


def test_parse_children_and_notifications_fixture():
    fixture = _fixture("children_and_notifications.json")
    assert parse_children_and_notifications(fixture["response_body"]) == [
        {"id": "101", "name": "Generated Child"}
    ]


def test_parse_children_and_notifications_fails_closed_for_non_ok_response():
    with pytest.raises(RuntimeError, match="not a successful"):
        parse_children_and_notifications("<html>login</html>")


def test_parse_week_schedule_assignment_fixture():
    fixture = _fixture("week_schedules.json")
    assert parse_week_schedule_assignment(fixture["response_body"], "2026-06-11", "101") == {
        "date": "2026-06-11",
        "child_id": "101",
        "pickup_id": None,
        "assignment_id": None,
        "version": None,
        "write_token": None,
        "write_supported": True,
        "block_reason": None,
        "schedule_id": "901",
        "start_ms": "28800000",
        "end_ms": "59400000",
    }


def test_parse_week_schedule_assignment_requires_requested_child():
    fixture = _fixture("week_schedules.json")
    with pytest.raises(RuntimeError, match="requested child/date"):
        parse_week_schedule_assignment(fixture["response_body"], "2026-06-11", "999")


def test_parse_assignment_write_success_fixture():
    fixture = _fixture("update_schedule_assignment.json")
    assert parse_assignment_write_response(fixture["response_body"]) == {
        "success": True,
    }


def test_parse_assignment_write_validation_error_fixture():
    fixture = _fixture("server_validation_error.json")
    with pytest.raises(RuntimeError, match="VALIDATION"):
        parse_assignment_write_response(fixture["response_body"])


def test_parse_assignment_malformed_or_expired_session_fixture():
    fixture = _fixture("malformed_non_ok.json")
    with pytest.raises(RuntimeError, match="not a successful"):
        parse_pickup_assignment(fixture["response_body"])
