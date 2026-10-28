"""Display domains must follow stored metadata, not the machine timezone."""
from copy import deepcopy
from datetime import datetime

import pytest
from PIL import ImageDraw

from mqlkiscanner import risiko_rechner as rr
from mqlkiscanner.studien_anzeigezeit import als_anzeigezeit, zeitachsen_label


@pytest.mark.parametrize('basis, label', [
    ({'frame': 'broker'}, 'CSV-/Brokerzeit'),
    ({'frame': 'referenzkurszeit'}, 'Referenzkurszeit (MT5-H1)'),
    ({}, 'Zeitbasis unbekannt'),
    (None, 'Zeitbasis unbekannt'),
    ({'frame': 'UTC'}, 'Zeitbasis unbekannt'),
    ({'frame': []}, 'Zeitbasis unbekannt'),
])
def test_png_labels_stored_domain_without_shifting_points(tmp_path, monkeypatch, basis, label):
    # CSV 12:00 with -2h reference shift still displays CSV 12:00, not 10:00 UTC.
    points = [{'t': 1767268800, 'equity': 1000, 'realisiert': 1000, 'messpunkt': True},
              {'t': 1767272400, 'equity': 900, 'realisiert': 900, 'messpunkt': True}]
    before = deepcopy(points)
    texts = []
    original = ImageDraw.ImageDraw.text

    def text(self, xy, content, *args, **kwargs):
        texts.append((xy, content))
        return original(self, xy, content, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', text)
    rr.kurve_png(tmp_path/'domain.png', points, 1000, zeitbasis=basis)
    assert label in [text for _, text in texts]
    assert '01.01. 12:00' in [text for xy, text in texts if 690 <= xy[1] < 730]
    assert not any('(UTC)' in text for _, text in texts)
    assert points == before


def test_pseudoepoch_decoder_does_not_attach_an_unproved_timezone():
    assert als_anzeigezeit(1767268800) == datetime(2026, 1, 1, 12)
    assert als_anzeigezeit(1767268800).tzinfo is None
    assert als_anzeigezeit(None) is None
    assert rr._epoch_text(1767268800) == '01.01.2026 12:00'
    assert zeitachsen_label(None) == 'Zeitbasis unbekannt'


def test_pdf_reports_the_same_time_domain_as_the_chart(tmp_path):
    from pypdf import PdfReader
    data = {'status': 'ok', 'zeitbasis': {'frame': 'broker'}, 'meta': {},
            'punkte': [], 'kennzahlen': {'startkapital': 1000}, 'statistik': {}}
    path, _ = rr.baue_pdf(data, tmp_path/'domain.pdf')
    text = ' '.join(' '.join(page.extract_text() or '' for page in PdfReader(path).pages).split())
    assert 'Zeitbasis der Kurve' in text and 'CSV-/Brokerzeit' in text
