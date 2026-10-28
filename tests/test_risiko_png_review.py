"""PNG regressions: the displayed risk must retain flows and unknown intervals."""
from copy import deepcopy

import pytest
from PIL import Image, ImageDraw

from mqlkiscanner import risiko_rechner as rr


def _punkt(hour, equity, *, flow=0, measured=True):
    return {'t': 1767225600 + hour * 3600, 'equity': equity,
            'realisiert': 1000 if equity is None else equity,
            'messpunkt': measured, 'flow_delta': flow}


@pytest.fixture
def drawing(monkeypatch):
    result = {'lines': [], 'text': []}
    original_line, original_text = ImageDraw.ImageDraw.line, ImageDraw.ImageDraw.text

    def line(self, xy, *args, **kwargs):
        result['lines'].append((kwargs.get('fill'), list(xy)))
        return original_line(self, xy, *args, **kwargs)

    def text(self, xy, content, *args, **kwargs):
        box = self.textbbox(xy, content, font=kwargs.get('font'))
        result['text'].append((xy, content, box))
        return original_text(self, xy, content, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'line', line)
    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', text)
    return result


@pytest.mark.parametrize('end, expected_pct', [(500, 0), (400, 20)])
def test_png_neutralisiert_auszahlung_und_zeigt_echten_verlust(tmp_path, drawing, end, expected_pct):
    points = [_punkt(0, 1000), _punkt(1, end, flow=-500)]
    before = deepcopy(points)
    rr.kurve_png(tmp_path/'flow.png', points, 1000)
    labels = [text for _, text, _ in drawing['text']]
    if expected_pct:
        assert f'\u2212{expected_pct},0 %' in labels
    else:
        assert not any(text.startswith('\u2212') and text.endswith(' %') for text in labels)
        red = [xy for color, xy in drawing['lines'] if color == (198, 40, 40)]
        assert red and all(y == 555 for xy in red for _, y in xy)
    assert points == before  # Renderer darf historische Studienpunkte nicht verändern.


def test_png_laesst_equity_und_unterwasser_an_messluecken_offen(tmp_path, drawing):
    points = [_punkt(0, 1000), _punkt(1, 900),
              _punkt(2, None, measured=False), _punkt(3, 800), _punkt(4, 1000)]
    rr.kurve_png(tmp_path/'gap.png', points, 1000)
    gap_x = 150 + (1400-150-30)/2
    for color in [(46, 125, 50), (198, 40, 40)]:
        segments = [xy for fill, xy in drawing['lines'] if fill == color]
        assert len(segments) == 2
        assert all(not (min(x for x, _ in xy) < gap_x < max(x for x, _ in xy))
                   for xy in segments)
    assert '\u221220,0 %' in [text for _, text, _ in drawing['text']]


def test_png_uebertraegt_auszahlung_bei_unbekannter_equity(tmp_path, drawing):
    points = [_punkt(0, 1000), _punkt(1, None, flow=-500, measured=False), _punkt(2, 400)]
    rr.kurve_png(tmp_path/'pending-flow.png', points, 1000)
    labels = [text for _, text, _ in drawing['text']]
    assert '\u221220,0 %' in labels
    assert '\u221260,0 %' not in labels


@pytest.mark.parametrize('hours', [0, 1, 24*180, 24*900])
def test_zeitlabels_bleiben_im_bild_auch_bei_einem_zeitpunkt(tmp_path, drawing, hours):
    points = [_punkt(0, 100000)] if hours == 0 else [_punkt(0, 100000), _punkt(hours, 90000)]
    rr.kurve_png(tmp_path/'axis.png', points, 100000)
    time_labels = [(text, box) for xy, text, box in drawing['text'] if 690 <= xy[1] < 730]
    assert len(time_labels) == (1 if hours == 0 else 5)
    assert all(0 <= box[0] <= box[2] <= 1400 for _, box in time_labels)
    assert not any('(UTC)' in text for text, _ in time_labels)
    assert 'Zeitbasis unbekannt' in [text for _, text, _ in drawing['text']]


def test_leere_kurve_ist_renderbar(tmp_path):
    path = tmp_path/'empty.png'
    rr.kurve_png(path, [], 1000)
    with Image.open(path) as image:
        assert image.size == (1400, 760)
