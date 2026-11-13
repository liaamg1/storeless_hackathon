"""Real PDF rasterization and hashing; no model downloads or development records."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from app.processors import presentation_processor as processor
from app.processors.presentation_processor import PresentationProcessingError, extract_slides
from app.processors.slide_hash import perceptual_distance
from app.schemas.presentation import PresentationRecord
from app.services.slide_comparison import compare_slides


def make_pdf(path, *, number='42', metadata='', different=False, blank=False):
    with pymupdf.open() as doc:
        page = doc.new_page(width=960, height=540)
        if not blank:
            page.draw_rect((30, 30, 930, 115), color=None, fill=(.05,.15,.3))
            page.insert_text((60, 90), 'Network architecture', fontsize=32, color=(1,1,1))
            page.insert_text((60, 180), 'Active components: ' + number, fontsize=24)
            page.draw_rect((60, 230, 350, 440), fill=(.1,.5,.8))
            page.draw_circle((650, 330), 90, fill=(.3,.7,.5))
            if different:
                page.draw_rect((0, 0, 960, 540), color=None, fill=(.8,.2,.2))
                page.draw_circle((160, 180), 140, fill=(1,1,1))
        doc.set_metadata({'title': metadata})
        doc.save(path)


def test_render_count_and_normalized_exact_matches_ignore_pdf_metadata(tmp_path):
    first, second = tmp_path/'one.pdf', tmp_path/'two.pdf'
    make_pdf(first, metadata='One')
    make_pdf(second, metadata='A different title')
    before = first.read_bytes()
    a = list(extract_slides(first, 'pdf', tmp_path/'a'))
    b = list(extract_slides(second, 'pdf', tmp_path/'b'))
    assert len(a) == len(b) == 1
    assert first.read_bytes() == before
    assert a[0].content_hash == b[0].content_hash
    assert a[0].perceptual_hash == b[0].perceptual_hash
    assert '42' in a[0].text
    assert a[0].thumbnail_path.is_file() and a[0].image_path.is_file()
    image = pymupdf.Pixmap(str(a[0].thumbnail_path))
    assert (image.width, image.height) == (480, 360)


def test_real_minor_change_is_similar_but_never_exact(tmp_path):
    one, two = tmp_path/'one.pdf', tmp_path/'two.pdf'
    make_pdf(one, number='42'); make_pdf(two, number='43')
    a = list(extract_slides(one, 'pdf', tmp_path/'a'))[0]
    b = list(extract_slides(two, 'pdf', tmp_path/'b'))[0]
    assert a.content_hash != b.content_hash
    assert (1 - perceptual_distance(a.perceptual_hash, b.perceptual_hash)/64)*100 >= 90


def test_clearly_different_slides_have_different_perceptual_hashes(tmp_path):
    one, two = tmp_path/'one.pdf', tmp_path/'two.pdf'
    make_pdf(one); make_pdf(two, different=True)
    a = list(extract_slides(one, 'pdf', tmp_path/'a'))[0]
    b = list(extract_slides(two, 'pdf', tmp_path/'b'))[0]
    assert perceptual_distance(a.perceptual_hash, b.perceptual_hash) > 6


def test_image_only_and_blank_pages_are_supported(tmp_path):
    pdf = tmp_path/'image.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0,0,100,100), False)
        pixmap.clear_with(120)
        page.insert_image((0,0,100,100), stream=pixmap.tobytes('png'))
        doc.new_page()
        doc.save(pdf)
    slides = list(extract_slides(pdf, 'pdf', tmp_path/'out'))
    assert len(slides) == 2
    assert all(slide.text == '' and slide.image_path.is_file() for slide in slides)


def test_page_limit_and_corrupt_pdfs(tmp_path):
    pdf = tmp_path/'file.pdf'
    make_pdf(pdf)
    with pytest.raises(PresentationProcessingError):
        list(extract_slides(pdf, 'pdf', tmp_path/'a', max_slides=0))
    pdf.write_bytes(b'corrupted')
    with pytest.raises(PresentationProcessingError):
        list(extract_slides(pdf, 'pdf', tmp_path/'b'))


def pptx_bytes():
    from presentation_fixtures import make_pptx
    return make_pptx()


def test_pptx_conversion_is_headless_and_uses_isolated_profile(tmp_path, monkeypatch):
    pptx = tmp_path/'input.pptx'; pptx.write_bytes(pptx_bytes())
    def run(args, **kwargs):
        assert '--headless' in args and 'pdf:impress_pdf_Export' in args
        assert any(arg.startswith('-env:UserInstallation=file:') for arg in args)
        assert kwargs['timeout'] == 120 and kwargs['check'] is True
        assert 'shell' not in kwargs
        output = Path(args[args.index('--outdir')+1])/'input.pdf'
        make_pdf(output)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(processor.subprocess, 'run', run)
    assert len(list(extract_slides(pptx, 'pptx', tmp_path/'out'))) == 1
    assert pptx.read_bytes() == pptx_bytes()


@pytest.mark.parametrize('error,message', [
    (FileNotFoundError(), 'LibreOffice'),
    (subprocess.TimeoutExpired('office',120), 'time limit'),
    (subprocess.CalledProcessError(1,'office'), 'could not convert'),
])
def test_conversion_failures_are_safe(tmp_path, monkeypatch, error, message):
    source = tmp_path/'source.pptx'; source.write_bytes(pptx_bytes())
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(processor.subprocess, 'run', fail)
    with pytest.raises(PresentationProcessingError, match=message):
        processor.convert_pptx(source,tmp_path,'office',120)
    assert source.is_file()


def test_invalid_pptx_is_rejected(tmp_path):
    path=tmp_path/'bad.pptx'; path.write_bytes(b'not a zip file')
    with pytest.raises(PresentationProcessingError): processor.validate_pptx(path)


def row(id, file_id, exact, perceptual):
    return dict(id=id, file_id=file_id, filename=f'file-{file_id}.pdf', slide_number=id,
                text='Slide content', processed_at=datetime.now(timezone.utc),
                content_hash=exact, perceptual_hash=perceptual)


def presentation():
    return PresentationRecord(file_id=1, filename='one.pdf', size_bytes=100, uploaded_at=None,
                              job_id=1,status='completed',current_step='completed',error_message=None,slide_count=3)


def test_exact_similar_unique_classification_and_no_self_matches():
    slides = [row(1,1,'a','0000000000000000'), row(2,1,'b','0000000000000001'), row(3,1,'c','ffffffffffffffff'),
              row(4,2,'a','0000000000000000')]
    result = compare_slides(presentation(),slides,90)
    assert [r.classification for r in result.slides] == ['exact','similar','unique']
    assert result.summary.exact_slides == result.summary.similar_slides == result.summary.unique_slides == 1
    assert result.summary.presentations_analyzed == 2 and result.summary.matching_presentations == 1
    assert all(match.slide.file_id != 1 for slide in result.slides for match in slide.matches)
    assert result.slides[1].matches[0].similarity_percent == 98.44


def test_perceptual_collision_is_only_similar_and_threshold_is_configurable():
    slides = [row(1,1,'changed-number','0000000000000000'),row(2,2,'original-number','0000000000000000')]
    assert compare_slides(presentation(),slides,100).slides[0].classification == 'similar'
    slides[1]['perceptual_hash']='0000000000000001'
    assert compare_slides(presentation(),slides,100).slides[0].classification == 'unique'
    assert compare_slides(presentation(),slides,90).slides[0].classification == 'similar'


def test_real_libreoffice_converts_pptx_when_installed(tmp_path):
    import shutil
    from presentation_fixtures import make_pptx
    if not shutil.which('libreoffice'):
        pytest.skip('Install LibreOffice Impress for real PPTX conversion test')
    pptx=tmp_path/'real.pptx';pptx.write_bytes(make_pptx(('First slide','Second slide')))
    slides=list(extract_slides(pptx,'pptx',tmp_path/'out'))
    assert len(slides)==2
    assert 'First slide' in slides[0].text and 'Second slide' in slides[1].text


def test_repeated_pages_in_same_presentation_are_not_cross_presentation_matches():
    result=compare_slides(presentation(),[row(1,1,'same','0000000000000000'),row(2,1,'same','0000000000000000')],90)
    assert result.summary.unique_slides==2 and result.summary.matching_presentations==0


def test_visible_annotations_are_included_in_exact_content_hash(tmp_path):
    one,two=tmp_path/'base.pdf',tmp_path/'annotated.pdf'
    make_pdf(one,blank=True)
    with pymupdf.open(one) as doc:
        annotation=doc[0].add_freetext_annot((60,60,600,120),'Cost changed to 43',fontsize=24)
        annotation.update()
        doc.save(two)
    plain=list(extract_slides(one,'pdf',tmp_path/'plain'))[0]
    annotated=list(extract_slides(two,'pdf',tmp_path/'annotated'))[0]
    assert plain.content_hash != annotated.content_hash
