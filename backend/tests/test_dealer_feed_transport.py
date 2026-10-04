"""Private pilot Basic Auth and company API feed key use separate headers."""
from test_dealer_feed_policies import _add_user,_add_company,_login,_csrf


def test_secondary_feed_key_works_without_replacing_pilot_basic_auth(integration):
    owner_id,email=_add_user(integration['SessionLocal'],label='secondary-feed-owner');_add_company(integration['SessionLocal'],owner_id);client,csrf=_login(integration,email)
    created=client.post('/api/v1/dealer/feeds',json={'name':'Local API transport','format':'api'},headers=_csrf(csrf));assert created.status_code==200
    feed_id=created.json()['feed']['id'];token=created.json()['api_token'];path=f'/api/v1/dealer/feeds/{feed_id}/api-imports'
    body={'items':[{'dealer_external_id':'LOCAL-TRANSPORT','manual_make':'Synthetic','manual_model':'Fixture','title':'Local only'}],'dry_run':True}
    result=client.post(path,json=body,headers={'Authorization':'Basic cGlsb3Q6bG9jYWw=','X-Dealer-Feed-Token':token,'Idempotency-Key':'secondary-valid'})
    assert result.status_code==200,result.text
    wrong=client.post(path,json=body,headers={'Authorization':'Basic cGlsb3Q6bG9jYWw=','X-Dealer-Feed-Token':'invalid-feed-key','Idempotency-Key':'secondary-invalid'})
    assert wrong.status_code==401
    assert token not in wrong.text
    ambiguous=client.post(path,json=body,headers={'Authorization':'Bearer invalid-feed-key','X-Dealer-Feed-Token':token,'Idempotency-Key':'secondary-ambiguous'})
    assert ambiguous.status_code==401
