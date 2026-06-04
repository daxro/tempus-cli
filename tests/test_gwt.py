from tempus_cli.gwt import parse_identity_providers, parse_schemas, payload_get_grand_id_identity_providers, payload_get_schemas

SCHEMAS = '//OK[14,938,13,2,12,727,11,2,10,399,9,2,8,275,7,2,6,23,5,2,4,20,3,2,6,1,["java.util.ArrayList/4159755760","se.tempus.common.shared.wrapper.Schema/2582274289","Sandsborgs Montessori","tempus-sandsborgsm","Miro Kids","tempus-stockholm-miro-kids","Katarina Barnstugeförening","tempus-stockholm-katarina","Stockholms stad","tempus-stockholm","Framtidsfolket Cosmos","tempus-stockholm-framtidsfolket","Stockholms stad OB","tempus-stockholm-ob"],0,7]'
PROVIDERS = '//OK[0,3,5,4,3,0,2,1,1,["java.util.ArrayList/4159755760","se.tempus.common.shared.grandid.SelectableGrandIdIdp/2371313207","Stockholm-inlogg","se.tempus.common.shared.login.LoginOption/2533300465","STOCKHOLM_PROD"],0,7]'


def test_payloads_match_observed_shape():
    assert payload_get_schemas("P", 12) == '7|0|5|https://home.tempusinfo.se/tempusHome/tempusHome/|P|se.limesaudio.tempushome.client.HomeService|getSchemas|I|1|2|3|4|1|5|12|'
    assert "getGrandIdIdentityProviders" in payload_get_grand_id_identity_providers("P", 399)


def test_parse_schemas():
    rows = parse_schemas(SCHEMAS)
    assert {r["name"]: r["id"] for r in rows}["Stockholms stad"] == 399


def test_parse_identity_providers():
    assert parse_identity_providers(PROVIDERS) == [{"name":"Stockholm-inlogg", "option":"STOCKHOLM_PROD"}]
