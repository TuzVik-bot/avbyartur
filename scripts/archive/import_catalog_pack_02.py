"""Add supplied pack 02 to the existing catalog. Dry run rolls back by default.

Archive SQL/scripts are never executed. Original source metadata is retained;
reference taxonomy and exact-variant specs are stored without changing listing rules.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from app.db import SessionLocal
from app.models import CatalogImport, CatalogMake, CatalogModel

SOURCE = 'Autorinok catalog pack 02'
SECTION_MAP = {'truck':'trucks', 'commercial':'trucks', 'bus':'buses',
               'motorcycle':'motorcycles', 'atv':'motorcycles', 'snow':'motorcycles',
               'boat':'watercraft', 'trailer':'trailers', 'special':'special_equipment',
               'agro':'agricultural_equipment'}


def normalize(value):
    decomposed = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(c for c in decomposed if c.isalnum())


def load_archive(path):
    files = ['00_sections.csv','00_categories_full.csv','00_category_sections.csv',
             '01_brands_full.csv','01_brands_metadata.csv','01_brand_aliases.csv',
             '02_brand_categories_full.csv','03_models_full.csv','03_models_metadata.csv',
             '03_excluded_passenger_rows.csv','04_attributes_full.csv',
             '04_attribute_category_rules.csv','06_variants_verified.csv','07_verified_specs.csv']
    with zipfile.ZipFile(path) as archive:
        data = {name:list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig')))) for name in files}
    for file,key,count in [('01_brands_full.csv','brand_id',109),('03_models_full.csv','model_id',820),('00_categories_full.csv','category_id',263)]:
        rows = data[file]
        assert len(rows)==count and len({r[key] for r in rows})==count, file
    brand_ids = {r['brand_id'] for r in data['01_brands_full.csv']}
    category_ids = {r['category_id'] for r in data['00_categories_full.csv']}
    model_ids = {r['model_id'] for r in data['03_models_full.csv']}
    assert not model_ids & {r['model_id'] for r in data['03_excluded_passenger_rows.csv']}
    assert len(data['03_models_metadata.csv'])==820
    assert {r['model_id'] for r in data['03_models_metadata.csv']}==model_ids
    for row in data['03_models_full.csv']:
        assert row['brand_id'] in brand_ids and row['category_id'] in category_ids
        assert row['model_name'].strip() and len(row['model_name'])<=180
        assert not row['year_from'] and not row['year_to'] and not row['model_variant']
    for row in data['02_brand_categories_full.csv']:
        assert row['brand_id'] in brand_ids and row['category_id'] in category_ids
    for row in data['01_brand_aliases.csv']:
        assert row['brand_id'] in brand_ids
    variants={r['variant_id']:r for r in data['06_variants_verified.csv']}
    assert len(variants)==4
    for row in variants.values():
        assert row['model_id'] in model_ids
    for row in data['07_verified_specs.csv']:
        assert row['variant_id'] in variants and variants[row['variant_id']]['model_id']==row['model_id']
    return data


def save_metadata(row, value):
    if row.source_metadata == value:
        return False
    row.source_metadata = value
    return True


def run(path, apply=False):
    data = load_archive(path)
    checksum = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    section_by_category={r['category_id']:r['section_id'] for r in data['00_category_sections.csv']}
    def category(code):
        return SECTION_MAP.get(section_by_category[code])
    brands_meta={r['brand_id']:r for r in data['01_brands_metadata.csv']}
    models_meta={r['model_id']:r for r in data['03_models_metadata.csv']}
    links=defaultdict(list)
    aliases=defaultdict(list)
    for row in data['02_brand_categories_full.csv']: links[row['brand_id']].append(row['category_id'])
    for row in data['01_brand_aliases.csv']: aliases[row['brand_id']].append(row['alias'])
    stats=Counter()
    with SessionLocal() as db:
        db.execute(text('select pg_advisory_xact_lock(74101501)'))
        makes=list(db.scalars(select(CatalogMake)))
        by_brand={}
        for raw in data['01_brands_full.csv']:
            key=normalize(raw['brand_name'])
            matches=[m for m in makes if m.external_id==raw['brand_id']]
            if not matches:
                matches=[m for m in makes if key in {normalize(m.name),normalize(m.slug),*(normalize(a) for a in m.aliases or [])}]
            assert len(matches)<=1, f"Ambiguous brand: {raw['brand_id']}"
            if matches:
                make=matches[0]; stats['makes_reused']+=1
            else:
                slug=re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',raw['brand_name']).encode('ascii','ignore').decode().lower()).strip('-')
                if not slug or any(m.slug==slug for m in makes): slug=raw['brand_id']
                make=CatalogMake(id=uuid5(NAMESPACE_URL,SOURCE+raw['brand_id']),slug=slug,name=raw['brand_name'],external_id=raw['brand_id'],source_name=SOURCE,aliases=[],manual_override=False)
                db.add(make); db.flush(); makes.append(make); stats['makes_created']+=1
            by_brand[raw['brand_id']]=make
            new_aliases=list(dict.fromkeys([*(make.aliases or []),*aliases[raw['brand_id']]]))
            if new_aliases != make.aliases:
                make.aliases=new_aliases; stats['make_alias_lists_updated']+=1
            metadata=dict(make.source_metadata or {})
            metadata['category_codes']=sorted(set(metadata.get('category_codes',[])) | {category(c) for c in links[raw['brand_id']] if category(c)})
            metadata['catalog_pack_02']={'record':raw,'metadata':brands_meta[raw['brand_id']],'category_ids':links[raw['brand_id']],'aliases':aliases[raw['brand_id']],'archive_sha256':checksum}
            stats['makes_metadata_updated']+=save_metadata(make,metadata)
        all_models=list(db.scalars(select(CatalogModel)))
        for raw in data['03_models_full.csv']:
            make=by_brand[raw['brand_id']]
            matches=[m for m in all_models if m.external_id==raw['model_id']]
            if not matches:
                matches=[m for m in all_models if m.make_id==make.id and normalize(raw['model_name']) in {normalize(m.name),normalize(m.slug),*(normalize(a) for a in m.aliases or [])}]
            assert len(matches)<=1, f"Ambiguous model: {raw['model_id']}"
            reused=bool(matches)
            if matches:
                model=matches[0]; assert model.make_id==make.id; stats['models_reused']+=1
            else:
                model=CatalogModel(id=uuid5(NAMESPACE_URL,SOURCE+raw['model_id']),make_id=make.id,slug=raw['model_id'],name=raw['model_name'],external_id=raw['model_id'],source_name=SOURCE,aliases=[],manual_override=False)
                db.add(model); all_models.append(model); stats['models_created']+=1
            metadata=dict(model.source_metadata or {})
            codes=set(metadata.get('category_codes',[]))
            mapped=category(raw['category_id'])
            visible=models_meta[raw['model_id']]['import_visibility']=='public_catalog'
            # Preserve prior pack-01 visibility; never label source_raw as verified.
            if mapped and visible: codes.add(mapped)
            metadata['category_codes']=sorted(codes)
            metadata['catalog_pack_02']={'record':raw,'metadata':models_meta[raw['model_id']],'archive_sha256':checksum,
                'variants':[r for r in data['06_variants_verified.csv'] if r['model_id']==raw['model_id']],
                'specs':[r for r in data['07_verified_specs.csv'] if r['model_id']==raw['model_id']]}
            stats['models_metadata_updated']+=save_metadata(model,metadata)
            stats['models_'+(mapped or 'unmapped')]+=1
            if not reused and not visible: stats['new_models_review_only']+=1
        # Correct category membership, retaining IDs, original records and any listing references.
        for raw in data['03_excluded_passenger_rows.csv']:
            model=next((m for m in all_models if m.external_id==raw['model_id']),None)
            if model:
                metadata=dict(model.source_metadata or {})
                metadata['category_codes']=[c for c in metadata.get('category_codes',[]) if c!='trucks']
                metadata['catalog_pack_02_exclusion']={**raw,'archive_sha256':checksum}
                stats['excluded_memberships_updated']+=save_metadata(model,metadata)
                stats['excluded_rows_preserved']+=1
        db.flush()
        if db.scalar(select(CatalogImport).where(CatalogImport.source_name==SOURCE,CatalogImport.checksum==checksum)) is None:
            db.add(CatalogImport(source_name=SOURCE,schema_version=2,checksum=checksum,counts=dict(stats),source_metadata={
                'archive':Path(path).name,'section_map':SECTION_MAP,
                'reference_data':{k:v for k,v in data.items() if k not in {'03_models_full.csv','03_models_metadata.csv'}},
                'notes':'User-supplied catalog; source claims retained without independent verification. Exact-variant specs are reference metadata only; listing fields and production years unchanged.'}))
        if apply: db.commit()
        else: db.rollback()
    return {'applied':apply,'archive_sha256':checksum,'counts':dict(stats)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.archive,args.apply),ensure_ascii=False))
