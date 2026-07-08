"""Regression tests for multi-cabinet drawer pairing in the viewer JS.

In project scenes every cabinet reuses the same node names; Three.js
GLTFLoader dedupes the repeats by appending _1, _2, … and the old match
regexes rejected those, so only the first cabinet's drawers animated.
Pair keys also collided across cabinets.  These tests pin the templated
JS: dedup-suffix-tolerant regexes and parent-uuid-scoped pair keys.
"""

import re

from cadquery_furniture.visualize import _build_html

HTML = _build_html("t", "AAAA", {})


def _js():
    return re.search(r'<script type="module">(.*?)</script>', HTML, re.S).group(1)


class TestPairingRegexes:
    def test_face_drawer_regex_accepts_dedup_suffix(self):
        js = _js()
        pattern = r"/^bay(\d+)_(face|drawer)(\d+)(?:_\d+)?$/"
        assert pattern in js
        rx = re.compile(r"^bay(\d+)_(face|drawer)(\d+)(?:_\d+)?$")
        assert rx.match("bay0_face0")
        assert rx.match("bay0_face0_1")      # second cabinet, deduped
        assert rx.match("bay0_drawer3_2")    # third cabinet
        assert not rx.match("bay0_face0_part_0")   # leaf mesh
        assert not rx.match("bay0_face0_part")     # wrapper group

    def test_pull_regex_is_group_anchored(self):
        js = _js()
        pattern = r"/^bay(\d+)_pull(\d+)_\d+(?:_\d+)?$/"
        assert pattern in js
        rx = re.compile(r"^bay(\d+)_pull(\d+)_\d+(?:_\d+)?$")
        assert rx.match("bay0_pull0_0")
        assert rx.match("bay0_pull0_0_1")    # deduped group
        assert not rx.match("bay0_pull0_0_part_0")  # leaf mesh
        # drawer index j is the second capture either way
        assert rx.match("bay0_pull2_0_1").group(2) == "2"

    def test_door_regex_accepts_dedup_suffix(self):
        rx = re.compile(r"^bay\d+_door\d+(_\d+){0,2}$")
        assert r"/^bay\d+_door\d+(_\d+){0,2}$/" in _js()
        assert rx.match("bay0_door0")        # single door
        assert rx.match("bay0_door0_1")      # pair leaf OR deduped single
        assert rx.match("bay0_door0_1_1")    # deduped pair leaf

    def test_pair_keys_scoped_by_parent_uuid(self):
        js = _js()
        assert js.count("grp.parent ? grp.parent.uuid : ''") == 2  # face/drawer + pull

    def test_pull_groups_deduplicated(self):
        assert "if (!pair.pulls.includes(grp)) pair.pulls.push(grp);" in _js()


class TestDiagColorClassifiers:
    def test_drawer_regex_tolerates_dedup_suffix(self):
        js = _js()
        assert r"const DIAG_DRAWER_RE = /^bay\d+_drawer\d+(?:_\d+)?$/;" in js

    def test_faces_and_doors_get_diag_color(self):
        js = _js()
        assert r"const DIAG_FACE_RE   = /^bay\d+_(face|door)\d+/;" in js
        assert "const PURPLE" in js

    def test_carcass_group_gate_removed(self):
        # top/bottom are siblings of bay_0, so the old ^bay_\d+$ gate
        # structurally excluded them — it must stay gone.
        assert r"/^bay_\d+$/" not in _js()

    def test_diag_material_is_flat_over_finishes(self):
        js = _js()
        assert "diagMat.map = null;" in js
        assert "diagMat.vertexColors = false;" in js
