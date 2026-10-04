"""Malformed legacy audit details must fail closed without breaking history reads."""
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from app.listing_change_audit import project_listing_change_event


@pytest.mark.parametrize('details',[
 {'changes':None},
 {'changes':[{'field':['vin'],'before':'secret','after':'secret'}]},
 {'changes':[{'field':'description','before':{'length':'broken'},'after':{}}]},
 {'changes':[{'field':'photos','before':{'items':None,'count':'broken'},'after':{}}]},
 {'changes':[{'field':'photos','before':{'items':[{'position':{'bad':True}}]},'after':{}}]},
 {'changed_field_keys':None},
 {'changed_field_keys':[{'field':'vin'}]},
 {'revision':True},
])
def test_legacy_listing_history_never_crashes_or_reveals_arbitrary_payload(details):
    event=SimpleNamespace(entity_type='listing',action='listing_edited',created_at=datetime.now(timezone.utc),details={'revision':2,'reason':'seller_edit','changed_field_keys':[],'changes':[],**details})
    result=project_listing_change_event(event)
    if details.get('revision') is True:
        assert result is None
    if result is not None:
        assert 'secret' not in str(result.model_dump())
        assert type(result.revision) is int and result.revision>=1
