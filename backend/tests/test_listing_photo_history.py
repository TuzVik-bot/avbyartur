"""Photo edits persist safe immutable moderator-visible history."""
import io,uuid
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.models import AuditEvent,Listing,ListingPhoto,User
from app.security import hash_password

PASSWORD='photo-history-test-password'


def test_photo_mutations_have_safe_history_and_private_authorization(integration):
    factory=integration['SessionLocal'];app=integration['client'].app
    actors={}
    with factory() as db:
        for role in ('user','moderator'):
            u=User(email=f'photo-history-{role}-{uuid.uuid4().hex}@example.com',display_name=role,password_hash=hash_password(PASSWORD),role=role,status='active');db.add(u);db.flush();actors[role]=(u.id,u.email)
        listing=Listing(owner_id=actors['user'][0],slug='photo-history-'+uuid.uuid4().hex,status='draft',revision=1,title='Local synthetic photo history',description='Local synthetic only',contact_phone='+375291234567',damaged=False,parts_only=False);db.add(listing);db.commit();lid=listing.id
    seller=TestClient(app,base_url='http://testserver');mod=TestClient(app,base_url='http://testserver');guest=TestClient(app,base_url='http://testserver')
    login=seller.post('/api/v1/auth/login',json={'email':actors['user'][1],'password':PASSWORD});headers={'X-CSRF-Token':login.json()['csrf_token']}
    buf=io.BytesIO();Image.new('RGB',(64,48),(20,90,120)).save(buf,'JPEG')
    ids=[]
    for n in range(2):
        r=seller.post(f'/api/v1/listings/{lid}/photos',files={'file':('private-original-name.jpg',buf.getvalue(),'image/jpeg')},headers={**headers,'Idempotency-Key':'photo-history-'+str(n)});assert r.status_code==200,r.text;ids.append(r.json()['id'])
    current=seller.get(f'/api/v1/listings/{lid}').json()['listing']
    r=seller.post(f'/api/v1/listings/{lid}/photos/reorder',json={'expected_revision':current['revision'],'photo_ids':ids[::-1]},headers=headers);assert r.status_code==200,r.text
    current=seller.get(f'/api/v1/listings/{lid}').json()['listing']
    r=seller.request('DELETE',f'/api/v1/listings/{lid}/photos/{ids[0]}',json={'expected_revision':current['revision']},headers=headers)
    assert r.status_code==200,r.text
    with factory() as db:
        events=db.scalars(select(AuditEvent).where(AuditEvent.entity_type=='listing',AuditEvent.entity_id==lid,AuditEvent.action=='listing_edited').order_by(AuditEvent.created_at)).all()
        assert len(events)==4
        assert all(e.details['changed_field_keys']==['photos'] for e in events)
        assert [e.details['changes'][0]['after']['count'] for e in events]==[1,2,2,1]
        assert 'private-original-name' not in str([e.details for e in events])
        assert 'storage_name' not in str([e.details for e in events])
    path=f'/api/v1/moderation/listings/{lid}/history'
    assert guest.get(path).status_code==401
    assert seller.get(path).status_code==403
    r=mod.post('/api/v1/auth/login',json={'email':actors['moderator'][1],'password':PASSWORD});assert r.status_code==200
    history=mod.get(path);assert history.status_code==200,history.text
    assert history.headers['cache-control']=='no-store'
    assert len(history.json()['items'])==4
    assert 'private-original-name' not in history.text


def test_company_seller_can_upload_but_viewer_cannot(integration):
    from app.models import Company,DealerTeamMember
    factory=integration['SessionLocal'];actors={}
    with factory() as db:
        for name in ('owner','seller','viewer'):
            user=User(email=f'company-photo-{name}-{uuid.uuid4().hex}@example.com',display_name=name,password_hash=hash_password(PASSWORD),role='user',status='active');db.add(user);db.flush();actors[name]=(user.id,user.email)
        company=Company(owner_id=actors['owner'][0],slug='company-photo-'+uuid.uuid4().hex,name='Synthetic company',unp='123456789',phone='+375291234567',address='Synthetic address',status='approved');db.add(company);db.flush()
        for role in ('seller','viewer'):db.add(DealerTeamMember(company_id=company.id,user_id=actors[role][0],role=role,status='active',granted_by=actors['owner'][0]))
        listing=Listing(owner_id=actors['owner'][0],company_id=company.id,slug='company-photo-listing-'+uuid.uuid4().hex,status='draft',revision=1,title='Synthetic company listing',description='Synthetic only',contact_phone='+375291234567',damaged=False,parts_only=False);db.add(listing);db.commit();lid=listing.id
    image=io.BytesIO();Image.new('RGB',(32,32),(10,40,60)).save(image,'JPEG')
    for role,expected in (('seller',200),('viewer',403)):
        client=TestClient(integration['client'].app,base_url='http://testserver');login=client.post('/api/v1/auth/login',json={'email':actors[role][1],'password':PASSWORD});assert login.status_code==200
        r=client.post(f'/api/v1/listings/{lid}/photos',files={'file':('local-synthetic.jpg',image.getvalue(),'image/jpeg')},headers={'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'company-photo-'+role});assert r.status_code==expected,r.text


def test_company_members_can_read_private_photo_status_and_processed_image(integration):
    from app.models import Company,DealerTeamMember
    factory=integration['SessionLocal'];actors={}
    with factory() as db:
        for name in ('owner','seller','viewer','outsider'):
            u=User(email=f'company-photo-read-{name}-{uuid.uuid4().hex}@example.com',display_name=name,password_hash=hash_password(PASSWORD),role='user',status='active');db.add(u);db.flush();actors[name]=(u.id,u.email)
        company=Company(owner_id=actors['owner'][0],slug='photo-read-company-'+uuid.uuid4().hex,name='Synthetic company',unp=str(100000000+uuid.uuid4().int%900000000),phone='+375291234567',address='Synthetic address',status='approved');db.add(company);db.flush()
        for role in ('seller','viewer'):db.add(DealerTeamMember(company_id=company.id,user_id=actors[role][0],role=role,status='active',granted_by=actors['owner'][0]))
        listing=Listing(owner_id=actors['owner'][0],company_id=company.id,slug='private-read-listing-'+uuid.uuid4().hex,status='draft',revision=1,title='Synthetic only',description='Synthetic only',contact_phone='+375291234567',damaged=False,parts_only=False);db.add(listing);db.flush();lid=listing.id
        photo=ListingPhoto(listing_id=lid,storage_name=uuid.uuid4().hex,original_name='private-name.upload',status='ready',position=0,is_cover=True,width=40,height=30);db.add(photo);db.commit();pid=photo.id;storage=photo.storage_name
    folder=integration['media_root']/storage;folder.mkdir();Image.new('RGB',(40,30),(10,20,30)).save(folder/'768.webp','WEBP')
    for role in ('seller','viewer','outsider'):
        client=TestClient(integration['client'].app,base_url='http://testserver');login=client.post('/api/v1/auth/login',json={'email':actors[role][1],'password':PASSWORD});assert login.status_code==200
        expected=404 if role=='outsider' else 200
        response=client.get(f'/api/v1/listings/{lid}/photos');assert response.status_code==expected,response.text
        image=client.get(f'/api/v1/photos/{pid}/768');assert image.status_code==expected
        if expected==200:assert image.headers['cache-control']=='no-store'
    guest=TestClient(integration['client'].app,base_url='http://testserver');assert guest.get(f'/api/v1/photos/{pid}/768').status_code==404
