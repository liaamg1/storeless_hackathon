"""Real database/API integration tests use only the disposable schema fixture."""
from pathlib import Path

import pytest
import pymupdf

from app.repositories import presentation_repository as repository
from app.services.presentation_service import process_presentation_job


def post_pdf(client, content, filename='slides.pdf'):
    response=client.post('/presentations/upload',files={'file':(filename,content,'application/pdf')})
    assert response.status_code==202,response.text
    return response.json()


def process_next():
    job=repository.claim_presentation_job()
    assert job is not None
    process_presentation_job(job)
    return job


def test_pdf_upload_analysis_comparison_relationships_and_images(database,client,pdf_bytes,uploads):
    content=pdf_bytes(('Network architecture 42','Another slide'))
    first=post_pdf(client,content,'first.pdf')
    job=process_next()
    assert job.file_id==first['file_id'] and job.storage_path.read_bytes()==content
    completed=client.get(f"/presentations/{job.file_id}").json()
    assert completed['status']=='completed' and completed['slide_count']==2
    second=post_pdf(client,content,'second.pdf')
    process_next()
    response=client.get(f"/presentations/{second['file_id']}/comparison")
    assert response.status_code==200
    data=response.json()
    assert data['summary']['exact_slides']==2
    assert data['summary']['matching_presentations']==1
    assert data['summary']['presentations_analyzed']==2
    assert all(match['slide']['file_id']==first['file_id'] for slide in data['slides'] for match in slide['matches'])
    slide_id=data['slides'][0]['slide']['id']
    image=client.get(f'/presentations/slides/{slide_id}/image')
    assert image.status_code==200 and image.headers['content-type']=='image/png'
    assert image.content.startswith(b'\x89PNG')
    with database() as connection:
        row=connection.execute('SELECT * FROM document_pages WHERE id=%s',(slide_id,)).fetchone()
        assert row['file_id']==second['file_id'] and len(row['content_hash'])==64
        assert len(row['perceptual_hash'])==16 and row['slide_processed_at'] is not None
        assert Path(row['image_path']).is_file() and Path(row['thumbnail_path']).is_file()
    # Analysis is idempotent: unchanged slides are not rendered again.
    before=Path(row['image_path']).stat().st_mtime_ns
    assert client.post(f"/presentations/{second['file_id']}/analyze").json()['status']=='completed'
    assert repository.claim_presentation_job() is None
    assert Path(row['image_path']).stat().st_mtime_ns==before


def test_existing_pdf_upload_is_automatically_queued_without_changing_extraction(database,client,pdf_bytes):
    source=pdf_bytes(('Original selectable text',))
    uploaded=client.post('/files/upload',files={'file':('existing.pdf',source,'application/pdf')})
    assert uploaded.status_code==201
    file_id=uploaded.json()['id']
    before=client.get(f'/files/{file_id}/pages').json()
    assert client.get(f'/presentations/{file_id}').json()['status']=='queued'
    process_next()
    assert client.get(f'/files/{file_id}/pages').json()==before
    assert client.get('/search',params={'q':'selectable'}).json()['results'][0]['file_id']==file_id


def test_existing_unprocessed_pdf_can_be_analyzed(database,client,pdf_bytes,uploads):
    path=uploads/'legacy.pdf';uploads.mkdir();path.write_bytes(pdf_bytes(('Legacy document',)))
    with database() as connection:
        row=connection.execute("INSERT INTO files(filename,size_bytes,sha256,storage_path) VALUES('legacy-real.pdf',100,'hash',%s) RETURNING id",(str(path),)).fetchone()
    file_id=row['id']
    assert client.get(f'/presentations/{file_id}').json()['status']=='not_processed'
    assert client.post(f'/presentations/{file_id}/analyze').status_code==202
    assert client.post(f'/presentations/{file_id}/analyze').json()['status']=='queued'
    process_next()
    assert client.get(f'/presentations/{file_id}').json()['status']=='completed'


def test_pptx_upload_and_background_conversion(database,client,monkeypatch,tmp_path):
    from app.processors import presentation_processor as processor
    from presentation_fixtures import make_pptx
    content=make_pptx()
    def convert(source,directory,binary,timeout):
        path=directory/'converted.pdf'
        with pymupdf.open() as doc:
            page=doc.new_page();page.insert_text((40,40),'Converted slide');doc.save(path)
        return path
    monkeypatch.setattr(processor,'convert_pptx',convert)
    response=client.post('/presentations/upload',files={'file':('deck.pptx',content,'application/vnd.openxmlformats-officedocument.presentationml.presentation')})
    assert response.status_code==202
    job=process_next()
    assert job.kind=='pptx' and job.storage_path.read_bytes()==content
    assert client.get(f'/presentations/{job.file_id}').json()['slide_count']==1
    search=client.get('/search',params={'q':'Converted'}).json()['results']
    assert search[0]['file_id']==job.file_id and search[0]['file_type']=='pptx'
    storage=client.get(f'/files/{job.file_id}/storage-savings').json()
    assert storage['optimized_size_bytes'] is None and storage['reduction_percent'] is None


def test_corrupt_pdf_fails_in_background_preserving_original(database,client):
    uploaded=post_pdf(client,b'%PDF-1.7 broken')
    job=process_next()
    result=client.get(f"/presentations/{uploaded['file_id']}").json()
    assert result['status']=='failed'
    assert job.storage_path.read_bytes()==b'%PDF-1.7 broken'
    assert client.get(f"/presentations/{uploaded['file_id']}/comparison").json()['slides']==[]


@pytest.mark.parametrize('filename,data,status', [('bad.pptx',b'broken zip',400),('notes.txt',b'not a deck',415),('empty.pdf',b'',400)])
def test_invalid_uploads_are_cleaned_up(database,client,uploads,filename,data,status):
    response=client.post('/presentations/upload',files={'file':(filename,data,'application/octet-stream')})
    assert response.status_code==status
    assert not [p for p in uploads.glob('*') if p.is_file()]
    with database() as connection:
        assert connection.execute("SELECT count(*) AS n FROM files WHERE filename=%s",(filename,)).fetchone()['n']==0


def test_no_development_records_are_modified_and_migration_is_repeatable(database):
    from conftest import ROOT
    with database() as connection:
        before=connection.execute('SELECT * FROM files ORDER BY id').fetchall()
        pages=connection.execute('SELECT * FROM document_pages ORDER BY id').fetchall()
    for _ in range(2):
        with database() as connection:
            connection.execute((ROOT/'database/migrations/006_slide_comparison.sql').read_text())
    with database() as connection:
        assert connection.execute('SELECT * FROM files ORDER BY id').fetchall()==before
        assert connection.execute('SELECT * FROM document_pages ORDER BY id').fetchall()==pages


def test_unknown_file_and_images(database,client):
    assert client.get('/presentations/999999').status_code==404
    assert client.get('/presentations/slides/999999/image').status_code==404
    assert client.post('/presentations/999999/analyze').status_code==404


def test_shared_worker_processes_presentation_queue(database,client,pdf_bytes,monkeypatch):
    from app import worker
    uploaded=post_pdf(client,pdf_bytes(('Queued background slide',)))
    monkeypatch.setattr(worker,'get_connection',database)
    monkeypatch.setattr(worker,'WORKER_LOCK_ID',92815043)
    monkeypatch.setattr(worker.signal,'signal',lambda *args:None)
    worker.run_worker(once=True)
    assert client.get(f"/presentations/{uploaded['file_id']}").json()['status']=='completed'


def test_persistence_failure_rolls_back_slide_metadata_and_preserves_source(database,client,pdf_bytes):
    uploaded=post_pdf(client,pdf_bytes(('Keep this source',)))
    with database() as connection:
        connection.execute('ALTER TABLE document_pages ADD CONSTRAINT reject_hash CHECK (content_hash IS NULL)')
    job=process_next()
    result=client.get(f"/presentations/{uploaded['file_id']}").json()
    assert result['status']=='failed' and job.storage_path.is_file()
    with database() as connection:
        assert connection.execute('SELECT count(*) AS n FROM document_pages WHERE file_id=%s',(job.file_id,)).fetchone()['n']==0


def test_image_endpoint_does_not_serve_original_or_arbitrary_paths(database,client,pdf_bytes):
    uploaded=post_pdf(client,pdf_bytes(('Source stays private',)))
    job=process_next()
    source_before=job.storage_path.read_bytes()
    with database() as connection:
        slide=connection.execute('UPDATE document_pages SET thumbnail_path=%s WHERE file_id=%s RETURNING id',(str(job.storage_path),job.file_id)).fetchone()
    assert client.get(f"/presentations/slides/{slide['id']}/image").status_code==404
    assert job.storage_path.read_bytes()==source_before
