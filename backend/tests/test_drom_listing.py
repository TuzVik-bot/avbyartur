import uuid

from app.models import (
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Listing,
    User,
)
from app.services import serialize_listings


def test_selected_drom_modification_and_long_generation_snapshot(integration):
    suffix = uuid.uuid4().hex[:8]
    generation_label = "01.2000 - 12.2005 " + "Frame code 123456789, " * 12
    with integration["SessionLocal"]() as db:
        owner = User(
            email=f"drom-listing-{suffix}@example.test",
            display_name="Drom seller",
            password_hash="test-only",
            role="user",
            status="active",
        )
        make = CatalogMake(slug=f"drom-make-{suffix}", name="Example", aliases=[])
        db.add_all([owner, make])
        db.flush()
        model = CatalogModel(
            make_id=make.id, slug=f"model-{suffix}", name="Example Model", aliases=[]
        )
        db.add(model)
        db.flush()
        generation = CatalogGeneration(
            model_id=model.id,
            slug=f"generation-{suffix}",
            name=generation_label,
            year_from=2000,
            year_to=2005,
        )
        db.add(generation)
        db.flush()
        modification = CatalogModification(
            generation_id=generation.id,
            slug=f"drom-{suffix}",
            name="2.0 MT",
            external_id=f"drom:{suffix}",
            source_name="Drom",
            source_metadata={
                "source": "drom.ru",
                "source_id": suffix,
                "source_url": f"https://www.drom.ru/catalog/example/model/{suffix}/",
                "trim": "2.0 MT",
                "engine_code": "E20",
                "frame_code": "R1",
                "engine_l": "2.0",
                "power_hp": "150",
                "fuel": "бензин",
                "transmission": "МКПП",
                "drive": "задний привод",
                "production_period": "01.2000 - 12.2005",
                "summary": "",
            },
            manual_override=False,
        )
        db.add(modification)
        db.flush()
        drom_listing = Listing(
            owner_id=owner.id,
            slug=f"drom-listing-{suffix}",
            status="active",
            make_id=make.id,
            model_id=model.id,
            generation_id=generation.id,
            modification_id=modification.id,
            make_name_snapshot=make.name,
            model_name_snapshot=model.name,
            generation_name_snapshot=generation.name,
            title="Example Model 2002",
            year=2002,
            description="Test listing",
            contact_phone="+375000000000",
        )
        manual_listing = Listing(
            owner_id=owner.id,
            slug=f"manual-listing-{suffix}",
            status="active",
            make_id=make.id,
            model_id=model.id,
            generation_id=generation.id,
            modification_id=None,
            make_name_snapshot=make.name,
            model_name_snapshot=model.name,
            generation_name_snapshot=generation.name,
            title="Manual example listing",
            year=2002,
            description="Test listing without selected trim",
            contact_phone="+375000000000",
        )
        db.add_all([drom_listing, manual_listing])
        db.commit()
        assert drom_listing.generation_name_snapshot == generation_label

        detail_response = integration["client"].get(
            f"/api/v1/listings/{drom_listing.id}"
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()["listing"]
        assert detail["modification"] == {
            "id": str(modification.id),
            "slug": modification.slug,
            "name": "2.0 MT",
            "source": {
                "name": "Drom",
                "id": suffix,
                "url": modification.source_metadata["source_url"],
            },
            "specs": {
                "engine_code": "E20",
                "frame_code": "R1",
                "engine_l": 2.0,
                "power_hp": 150,
                "fuel": "бензин",
                "transmission": "МКПП",
                "drive": "задний привод",
                "production_period_raw": "01.2000 - 12.2005",
                "summary_raw": None,
            },
        }

        manual_detail_response = integration["client"].get(
            f"/api/v1/listings/{manual_listing.id}"
        )
        assert manual_detail_response.status_code == 200
        assert manual_detail_response.json()["listing"]["modification"] is None

        search_summaries = serialize_listings(db, [drom_listing], public=True)
        assert "modification" not in search_summaries[0]
