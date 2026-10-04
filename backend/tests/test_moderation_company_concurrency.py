"""Moderation must wait for company scope before locking a company listing."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from fastapi.testclient import TestClient
from sqlalchemy import event,select
from sqlalchemy.exc import DBAPIError
from app.models import Company,Listing,User
from app.security import hash_password


def test_company_moderation_does_not_lock_listing_while_waiting_for_company(integration):
    factory=integration['SessionLocal'];engine=integration['engine'];password='moderation-company-fixture'
    with factory() as db:
        owner=User(email=f'owner-{uuid.uuid4().hex}@example.com',display_name='Owner',password_hash=hash_password(password),role='user',status='active');reviewer=User(email=f'mod-{uuid.uuid4().hex}@example.com',display_name='Moderator',password_hash=hash_password(password),role='moderator',status='active');db.add_all([owner,reviewer]);db.flush();email=reviewer.email
        company=Company(owner_id=owner.id,slug='company-'+uuid.uuid4().hex,name='Local synthetic company',unp=str(100000000+uuid.uuid4().int%900000000),phone='+375291234567',address='Synthetic address',status='approved');db.add(company);db.flush();cid=company.id
        listing=Listing(owner_id=owner.id,company_id=company.id,slug='mod-lock-'+uuid.uuid4().hex,title='Local synthetic',description='Test fixture only',contact_phone='+375291234567',status='pending_review',revision=1,submitted_revision=1,damaged=False,parts_only=False);db.add(listing);db.commit();lid=listing.id
    client=TestClient(integration['client'].app,base_url='http://testserver');login=client.post('/api/v1/auth/login',json={'email':email,'password':password});assert login.status_code==200
    attempted_company=Event()
    def observe(_conn,_cursor,statement,_params,_context,_many):
        if 'companies' in statement.casefold() and 'for update' in statement.casefold():attempted_company.set()
    with factory() as company_editor:
        company_editor.scalar(select(Company).where(Company.id==cid).with_for_update())
        event.listen(engine,'before_cursor_execute',observe)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(client.post,f'/api/v1/moderation/listings/{lid}/approve',json={'expected_revision':1},headers={'X-CSRF-Token':login.json()['csrf_token']})
                try:
                    assert attempted_company.wait(5),'approval did not reach company lock'
                    listing_unlocked=True
                    with factory() as seller_editor:
                        try:seller_editor.scalar(select(Listing).where(Listing.id==lid).with_for_update(nowait=True))
                        except DBAPIError as exc:
                            if getattr(exc.orig,'sqlstate',None)!='55P03':raise
                            listing_unlocked=False
                        finally:seller_editor.rollback()
                finally:company_editor.rollback()
                result=future.result(timeout=8)
                assert listing_unlocked,'Approval held Listing while blocked on Company, allowing edit/reveal deadlock'
                assert result.status_code==200,result.text
        finally:event.remove(engine,'before_cursor_execute',observe)
