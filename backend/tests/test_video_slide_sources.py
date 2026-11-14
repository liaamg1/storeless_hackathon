import numpy as np
import pymupdf

from app.services.video_slide_sources import image_hash


def save_image(path, pixels):
    path.parent.mkdir(parents=True, exist_ok=True)
    pymupdf.Pixmap(pymupdf.csRGB, pixels.shape[1], pixels.shape[0], pixels.tobytes(), False).save(str(path))


def diagram():
    pixels = np.full((240, 400, 3), 255, dtype=np.uint8)
    pixels[30:80, 20:180] = (25, 90, 180)
    pixels[110:210, 160:370] = (120, 40, 10)
    pixels[90:160, 200:250] = (0, 180, 40)
    return pixels


def test_same_visual_hash_across_letterbox_and_blank_skip(tmp_path):
    a, b, blank = tmp_path / 'a.png', tmp_path / 'b.png', tmp_path / 'blank.png'
    pixels = diagram()
    padded = np.pad(pixels, ((40, 40), (20, 20), (0, 0)), constant_values=255)
    save_image(a, pixels)
    save_image(b, padded)
    save_image(blank, np.full((50, 50, 3), 255, dtype=np.uint8))
    assert image_hash(a) == image_hash(b)
    assert image_hash(blank) is None


def test_source_candidates_use_completed_cached_images_without_changes(client, database, uploads):
    image = uploads / 'slides' / 'source.png'
    frame = uploads / 'visuals' / 'frame.png'
    save_image(image, diagram())
    save_image(frame, np.pad(diagram(), ((40, 40), (0, 0), (0, 0)), constant_values=255))
    before = image.read_bytes(), frame.read_bytes()
    with database() as connection:
        slide_file = connection.execute(
            "INSERT INTO files(filename,size_bytes,sha256) VALUES('source.pptx',100,'source') RETURNING id"
        ).fetchone()['id']
        connection.execute(
            "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,'presentation_analysis','completed')",
            (slide_file,),
        )
        slide_id = connection.execute(
            """INSERT INTO document_pages(file_id,page_number,extracted_text,image_path,content_hash,perceptual_hash)
            VALUES(%s,1,'diagram',%s,%s,%s) RETURNING id""",
            (slide_file, str(image), 'a' * 64, '0' * 16),
        ).fetchone()['id']
        video = connection.execute(
            "INSERT INTO files(filename,size_bytes,sha256,file_type) VALUES('recording.mp4',200,'video','video') RETURNING id"
        ).fetchone()['id']
        for kind in ('video_transcription', 'video_visuals'):
            connection.execute(
                "INSERT INTO processing_jobs(file_id,job_type,status) VALUES(%s,%s,'completed')",
                (video, kind),
            )
        frame_id = connection.execute(
            """INSERT INTO video_frames(file_id,start_ms,end_ms,image_path,image_hash,size_bytes)
            VALUES(%s,0,1000,%s,%s,%s) RETURNING id""",
            (video, str(frame), '0' * 16, frame.stat().st_size),
        ).fetchone()['id']
    response = client.get(f'/videos/{video}/slide-sources')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['slides_compared'] == 1
    assert data['frames'][0]['frame_id'] == frame_id
    match = data['frames'][0]['matches'][0]
    assert match['slide_id'] == slide_id and match['similarity_percent'] == 100
    assert match['filename'] == 'source.pptx' and 'image_path' not in response.text
    assert before == (image.read_bytes(), frame.read_bytes())
    frame.unlink()
    missing = client.get(f'/videos/{video}/slide-sources').json()
    assert missing['skipped_images'] == 1 and missing['frames'][0]['matches'] == []
    with database() as connection:
        connection.execute(
            "UPDATE processing_jobs SET status='processing' WHERE file_id=%s AND job_type='video_visuals'",
            (video,),
        )
    pending = client.get(f'/videos/{video}/slide-sources').json()
    assert pending['status'] == 'processing' and pending['frames'] == []
    assert client.get('/videos/999999/slide-sources').status_code == 404
